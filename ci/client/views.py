from django.views.decorators.csrf import csrf_exempt
from django.db.models import Sum
from django.http import JsonResponse, HttpResponseNotAllowed, HttpResponseBadRequest
import json
from django.core.urlresolvers import reverse
from ci import models, event
from ci.recipe import file_utils
import logging
from django.conf import settings
from django.db import transaction
from datetime import timedelta
logger = logging.getLogger('ci')

def update_status(job, status=None):
  if not status:
    job.status = event.job_status(job)
    job.save()
    status = event.event_status(job.event)
  else:
    job.status = status
    job.save()

  if job.event.status != models.JobStatus.CANCELED:
    job.event.status = status
  job.event.save() # save regardless to update timestamp

  if job.event.pull_request:
    job.event.pull_request.status = status
    job.event.pull_request.save()
  elif job.event.base.branch:
    job.event.base.branch.status = status
    job.event.base.branch.save()

def get_client_ip(request):
  x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
  if x_forwarded_for:
    ip = x_forwarded_for.split(',')[-1].strip()
  else:
    ip = request.META.get('REMOTE_ADDR')
  return ip

def ready_jobs(request, build_key, client_name):
  if request.method != 'GET':
    return HttpResponseNotAllowed(['GET'])

  client, created = models.Client.objects.get_or_create(name=client_name,ip=get_client_ip(request))
  if created:
    logger.debug('New client %s : %s seen' % (client_name, get_client_ip(request)))

  client.status_message = 'Looking for work'
  client.status = models.Client.IDLE
  client.save()

  jobs = models.Job.objects.filter(
      event__build_user__build_key=build_key,
      complete=False,
      active=True,
      ready=True,
      status=models.JobStatus.NOT_STARTED,
      ).order_by('-recipe__priority', 'created')
  jobs_json = []
  for job in jobs.select_related('config').all():
    data = {'id':job.pk,
        'build_key': build_key,
        'config': job.config.name,
        }
    jobs_json.append(data)

  reply = { 'jobs': jobs_json }
  return JsonResponse(reply)

def check_post(request, required_keys):
  if request.method != 'POST':
    return None, HttpResponseNotAllowed(['POST'])
  try:
    data = json.loads(request.body)
    required = set(required_keys)
    available = set(data.keys())
    if not required.issubset(available):
      logger.debug('Bad POST data.\nRequest: %s' % data)
      return data, HttpResponseBadRequest('Bad POST data')
    return data, None
  except ValueError:
    return None, HttpResponseBadRequest('Invalid JSON')


def get_job_info(job):
  """
  Gather all the information required to run a job to
  send to a client.
  We do it like this because we don't want the chance
  of the user changing the recipe while a job is running
  and causing problems.
  """
  job_dict = {
      'recipe_name': job.recipe.name,
      'job_id': job.pk,
      'abort_on_failure':job.recipe.abort_on_failure,
      }
  recipe_env = [
      ('job_id', job.pk),
      ('recipe_id', job.recipe.pk),
      ('comments_url', str(job.event.comments_url)),
      ('base_repo', str(job.event.base.repo())),
      ('base_ref', job.event.base.branch.name),
      ('base_sha', job.event.base.sha),
      ('base_ssh_url', str(job.event.base.ssh_url)),
      ('head_repo', str(job.event.head.repo())),
      ('head_ref', job.event.head.branch.name),
      ('head_sha', job.event.head.sha),
      ('head_ssh_url', str(job.event.head.ssh_url)),
      ('abort_on_failure', job.recipe.abort_on_failure),
      ('cause', job.recipe.cause_str()),
      ('config', job.config.name),
      ]

  for env in job.recipe.environment_vars.all():
    recipe_env.append((env.name, env.value))

  job_dict['environment'] = recipe_env

  base_file_dir = settings.RECIPE_BASE_DIR
  prestep_env = []
  for prestep in job.recipe.prestepsources.all():
    if prestep.filename:
      contents = file_utils.get_contents(base_file_dir, prestep.filename)
      if contents:
        prestep_env.append(contents)

  job_dict['prestep_sources'] = prestep_env

  job.step_results.all().delete()
  step_recipes = []
  for step in job.recipe.steps.order_by('position'):
    step_dict = {
        'step_num': step.position,
        'step_name': step.name,
        'step_abort_on_failure': step.abort_on_failure,
        'step_allowed_to_fail': step.allowed_to_fail,
        }

    step_result, created = models.StepResult.objects.get_or_create(
        job=job,
        name=step.name,
        position=step.position,
        abort_on_failure=step.abort_on_failure,
        allowed_to_fail=step.allowed_to_fail,
        filename=step.filename)

    if not created:
      return None
    logger.info('Created step result for {}: {}: {}: {}'.format(job.pk, job, step_result.pk, step.name))
    step_result.output = ''
    step_result.complete = False
    step_result.seconds = timedelta(seconds=0)
    step_result.status = models.JobStatus.NOT_STARTED
    step_result.save()
    step_dict['stepresult_id'] = step_result.pk

    step_env = []
    for env in step.step_environment.all():
      step_env.append((env.name, env.value))
    step_dict['environment'] = step_env
    if step.filename:
      contents = file_utils.get_contents(base_file_dir, step.filename)
      step_dict['script'] = str(contents) # in case of empty file, use str

    step_recipes.append(step_dict)

  job_dict['steps'] = step_recipes

  return job_dict

def json_claim_response(job_id, config_name, claimed, msg, job_info=None):
  return JsonResponse({
    'job_id': job_id,
    'config': config_name,
    'success': claimed,
    'message': msg,
    'status': 'OK',
    'job_info': job_info,
    })

def claim_job_check(request, build_key, config_name, client_name):
  data, response = check_post(request, ['job_id'])
  if response:
    return response, None, None, None

  try:
    config = models.BuildConfig.objects.get(name=config_name)
  except models.BuildConfig.DoesNotExist:
    err_str = 'Client {}: Invalid config {}'.format(client_name, config_name)
    logger.warning(err_str)
    return HttpResponseBadRequest(err_str), None, None, None

  try:
    logger.info('{} trying to get job {}'.format(client_name, data['job_id']))
    job = models.Job.objects.get(pk=int(data['job_id']),
        config=config,
        event__build_user__build_key=build_key,
        status=models.JobStatus.NOT_STARTED,
        )
  except models.Job.DoesNotExist:
    logger.warning('Client {} requested bad job {}'.format(client_name, data['job_id']))
    return HttpResponseBadRequest('No job found'), None, None, None
  return None, data, config, job

@csrf_exempt
@transaction.atomic
def claim_job(request, build_key, config_name, client_name):
  """
  Called by the client to claim a job.
  If multiple clients call this only one should get a valid response. The
  others should get a bad request response.
  """
  response, data, config, job = claim_job_check(request, build_key, config_name, client_name)
  if response:
    return response

  client_ip = get_client_ip(request)
  client, created = models.Client.objects.get_or_create(name=client_name, ip=client_ip)
  if created:
    logger.info('New client %s : %s seen' % (client_name, client_ip))

  if job.invalidated and job.same_client and job.client and job.client != client:
    logger.info('{} requested job {}: {} but waiting for client {}'.format(client, job.pk, job, job.client))
    return HttpResponseBadRequest('Wrong client')

  job.status = models.JobStatus.RUNNING
  job.save()

  job_info = get_job_info(job)

  if not job_info:
    logger.info('{} did not get job {}: {}'.format(client, job.pk, job))
    return HttpResponseBadRequest('Did not get the job')

  # The client definitely has the job now
  job.client = client
  job.save()
  job.event.status = models.JobStatus.RUNNING
  job.event.save()
  update_status(job, models.JobStatus.RUNNING)

  client.status = models.Client.RUNNING
  client.status_message = 'Job {}: {}'.format(job.pk, job)
  client.save()

  logger.info('Client %s got job %s: %s: on %s' % (client_name, job.pk, job, job.recipe.repository))

  if job.event.cause == models.Event.PULL_REQUEST:
    user = job.event.build_user
    oauth_session = user.server.auth().start_session_for_user(user)
    api = user.server.api()
    api.update_pr_status(
        oauth_session,
        job.event.base,
        job.event.head,
        api.PENDING,
        request.build_absolute_uri(reverse('ci:view_job', args=[job.pk])),
        'Starting',
        str(job),
        )
  return json_claim_response(job.pk, config_name, True, 'Success', job_info)

def json_finished_response(status, msg):
  return JsonResponse({'status': status, 'message': msg})

def add_comment(request, oauth_session, user, job):
  if job.event.cause != models.Event.PULL_REQUEST:
    return
  if not job.event.comments_url:
    return
  comment = 'Testing {}\n\n{} {}: **{}**\n'.format(job.event.head.sha, job.recipe.name, job.config, job.status_str())
  abs_job_url = request.build_absolute_uri(reverse('ci:view_job', args=[job.pk]))
  comment += '\nView the results [here]({}).\n'.format(abs_job_url)
  user.server.api().pr_comment(oauth_session, job.event.comments_url, comment)

def check_job_finished_post(request, build_key, client_name, job_id):
  data, response = check_post(request, ['seconds', 'complete'])

  if response:
    return response, None, None, None

  try:
    client = models.Client.objects.get(name=client_name, ip=get_client_ip(request))
  except models.Client.DoesNotExist:
    return HttpResponseBadRequest('Invalid client'), None, None, None

  try:
    job = models.Job.objects.get(pk=job_id, client=client, event__build_user__build_key=build_key)
  except models.Job.DoesNotExist:
    return HttpResponseBadRequest('Invalid job/build_key'), None, None, None

  return None, data, client, job

@csrf_exempt
def job_finished(request, build_key, client_name, job_id):
  response, data, client, job = check_job_finished_post(request, build_key, client_name, job_id)
  if response:
    return response

  job.seconds = timedelta(seconds=data['seconds'])
  job.complete = data['complete']
  job.save()

  update_status(job)

  client.status = models.Client.IDLE
  client.status_message = 'Finished job {}: {}'.format(job.pk, job)
  client.save()

  user = job.event.build_user
  oauth_session = user.server.auth().start_session_for_user(user)
  api = user.server.api()

  if job.event.cause == models.Event.PULL_REQUEST:
    status = api.SUCCESS
    msg = "Passed"
    if job.status == models.JobStatus.FAILED_OK:
      msg = "Failed but allowed"
    elif job.status == models.JobStatus.CANCELED:
      status = api.CANCELED
      msg = "Canceled"
    elif job.status == models.JobStatus.FAILED:
      status = api.FAILURE
      msg = "Failed"

    api.update_pr_status(
        oauth_session,
        job.event.base,
        job.event.head,
        status,
        request.build_absolute_uri(reverse('ci:view_job', args=[job.pk])),
        msg,
        str(job),
        )

  add_comment(request, oauth_session, user, job)

  # now check if all configs are finished
  all_complete = True
  for job in job.event.jobs.all():
    if not job.complete:
      all_complete = False
      break

  if all_complete:
    job.event.complete = True
    job.event.save()
  else:
    event.make_jobs_ready(job.event)
  return json_finished_response('OK', 'Success')

def json_update_response(status, msg, next_step=True, cmd=None):
  """
  status: current status of the job
  msg: "success" so that the client knows everything was handled properly
  next_step: true or false depending on whether the client should run the next step
  cmd : None or "cancel" if the job got canceled
  """
  data = {'status': status, 'message': msg, 'next_step': next_step, 'command': cmd}
  return JsonResponse(data)

def step_start_pr_status(request, step_result, job):
  """
  This gets called when the client starts a step.
  Just tries to update the status on the server.
  """

  if job.event.cause != models.Event.PULL_REQUEST:
    return

  user = job.event.build_user
  server = user.server
  oauth_session = server.auth().start_session_for_user(user)
  api = server.api()
  status = api.RUNNING
  desc = '({}/{}) {}'.format(step_result.position+1, job.step_results.count(), step_result.name)

  api.update_pr_status(
      oauth_session,
      job.event.base,
      job.event.head,
      status,
      request.build_absolute_uri(reverse('ci:view_job', args=[job.pk])),
      desc,
      str(job),
      )

def step_complete_pr_status(request, step_result, job):
  """
  This gets called when the client completes a step.
  Just tries to update the status on the server.
  This is mainly for updating the description on GitHub
  as the status isn't changed. GitLab doesn't seem
  to use the description anywhere so it probably
  isn't required to do this update but to avoid
  special casing git servers do it anyway.
  """

  if job.event.cause != models.Event.PULL_REQUEST:
    return

  user = job.event.build_user
  server = user.server
  oauth_session = server.auth().start_session_for_user(user)
  api = server.api()
  # Always keep the status as RUNNING, it will get set properly in job_finished.
  # GitLab doesn't seem to like setting FAILURE or CANCELED multiple times as
  # it creates a new "build" for each one.
  status = api.RUNNING

  desc = '(%s/%s) complete' % (step_result.position+1, job.step_results.count())
  if job.status == models.JobStatus.CANCELED:
    desc = 'Canceled'

  if step_result.exit_status != 0 and not step_result.allowed_to_fail:
    desc = '{} exited with code {}'.format(step_result.name, step_result.exit_status)

  api.update_pr_status(
      oauth_session,
      job.event.base,
      job.event.head,
      status,
      request.build_absolute_uri(reverse('ci:view_job', args=[job.pk])),
      desc,
      str(job),
      )


def check_step_result_post(request, build_key, client_name, stepresult_id):
  data, response = check_post(request,
      ['step_num', 'output', 'time', 'complete', 'exit_status'])

  if response:
    return response, None, None, None

  try:
    step_result = models.StepResult.objects.get(pk=stepresult_id)
  except models.StepResult.DoesNotExist:
    return HttpResponseBadRequest('Invalid stepresult id'), None, None, None

  try:
    client = models.Client.objects.get(name=client_name, ip=get_client_ip(request))
  except models.Client.DoesNotExist:
    return HttpResponseBadRequest('Invalid client'), None, None, None

  if client != step_result.job.client:
    return HttpResponseBadRequest('Same client that started is required'), None, None, None
  return None, data, step_result, client

@csrf_exempt
def start_step_result(request, build_key, client_name, stepresult_id):
  response, data, step_result, client = check_step_result_post(request, build_key, client_name, stepresult_id)
  if response:
    return response

  cmd = None
  # could have been canceled in between getting the job and starting the job
  status = models.JobStatus.RUNNING
  if step_result.job.status == models.JobStatus.CANCELED:
    status = models.JobStatus.CANCELED
    cmd = 'cancel'

  step_result.status = status
  step_result.save()
  step_result.job.save() # save to update timestamp
  update_status(step_result.job, status)
  client.status_msg = 'Starting {} on job {}'.format(step_result.name, step_result.job)
  client.save()
  step_start_pr_status(request, step_result, step_result.job)
  return json_update_response('OK', 'success', True, cmd)

def step_result_from_data(step_result, data, status):
  step_result.seconds = timedelta(seconds=data['time'])
  step_result.output = step_result.output + data['output']
  step_result.complete = data['complete']
  step_result.exit_status = int(data['exit_status'])
  step_result.status = status
  step_result.save()

@csrf_exempt
def complete_step_result(request, build_key, client_name, stepresult_id):
  response, data, step_result, client = check_step_result_post(request, build_key, client_name, stepresult_id)
  if response:
    return response

  status = models.JobStatus.SUCCESS
  next_step = True
  if data.get('canceled'):
    status = models.JobStatus.CANCELED
  elif data['exit_status'] != 0:
    status = models.JobStatus.FAILED
    next_step = False
    if step_result.allowed_to_fail:
      status = models.JobStatus.FAILED_OK
    if not step_result.abort_on_failure or not step_result.job.recipe.abort_on_failure:
      next_step = True

  step_result_from_data(step_result, data, status)
  job = step_result.job

  if data['complete']:
    step_result.output = data['output']
    step_result.save()

    client.status_msg = 'Completed {}: {}'.format(step_result.job, step_result.name)
    client.save()

    step_complete_pr_status(request, step_result, job)
  update_status(job, step_result.job.status)
  return json_update_response('OK', 'success', next_step)

@csrf_exempt
def update_step_result(request, build_key, client_name, stepresult_id):
  response, data, step_result, client = check_step_result_post(request, build_key, client_name, stepresult_id)
  if response:
    return response

  step_result_from_data(step_result, data, models.JobStatus.RUNNING)
  job = step_result.job
  next_step = True

  cmd = None
  # somebody canceled or invalidated the job
  if job.status == models.JobStatus.CANCELED or job.status == models.JobStatus.NOT_STARTED:
    step_result.status = job.status
    step_result.save()
    cmd = 'cancel'
    next_step = False

  update_status(step_result.job, step_result.job.status)
  client.status_msg = 'Running {} ({}): {} : {}'.format(step_result.job, step_result.job.pk, step_result.name, step_result.seconds)
  client.save()

  total = job.step_results.aggregate(Sum('seconds'))
  job.seconds = total['seconds__sum']
  job.save()

  return json_update_response('OK', 'success', next_step, cmd)
