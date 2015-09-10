from django.conf import settings
from django.utils import timezone
from django.http import JsonResponse, HttpResponseBadRequest, HttpResponseForbidden
from django.shortcuts import get_object_or_404
from ci import models
from ci.recipe import file_utils
from ci import views
import os, datetime
import logging
logger = logging.getLogger('ci')

def get_file(request):
  """
  We need to get the text of the file and send it back.
  """

  if 'filename' not in request.GET or 'user' not in request.GET:
    return HttpResponseBadRequest('Missing parameters')

  fname = request.GET['filename']
  user_name = request.GET['user']
  users = models.GitUser.objects.filter(name=user_name)
  allowed = False
  # FIXME: We are assuming a common user directory for all users
  # with the same name. Since we support multiple Git servers,
  # a user on one might not actually be the user on another.
  for user in users:
    signed_in = user.server.auth().signed_in_user(user.server, request.session)
    if user == signed_in:
      allowed = True
      break

  if not allowed:
    return HttpResponseForbidden('You do not have permission to see this file')

  if not file_utils.is_valid_file(settings.RECIPE_BASE_DIR, user.name, fname):
    logger.debug('Invalid file request: {}'.format(fname))
    return HttpResponseBadRequest('Invalid filename')

  try:
    full_name = os.path.join(settings.RECIPE_BASE_DIR, fname)
    ret = {'shared': file_utils.is_shared_file(settings.RECIPE_BASE_DIR, full_name)}
    with open(full_name, 'r') as f:
      data = f.read()
      ret['contents'] = data
      return JsonResponse(ret)
  except:
    return HttpResponseBadRequest('Not found')


def can_see_results(request, recipe):
  creator = recipe.creator
  signed_in = creator.server.auth().signed_in_user(creator.server, request.session)
  if recipe.private:
    if not signed_in:
      return HttpResponseForbidden('You need to sign in')

    if signed_in != creator:
      auth = signed_in.server.auth().start_session(request.session)
      collab = signed_in.server.api().is_collaborator(auth, signed_in, recipe.repository)
      if not collab:
        return HttpResponseForbidden('Not authorized to view these results')
  return None

def get_result_output(request):
  if 'result_id' not in request.GET:
    return HttpResponseBadRequest('Missing parameter')

  result_id = request.GET['result_id']

  result = get_object_or_404(models.StepResult, pk=result_id)
  ret = can_see_results(request, result.job.recipe)
  if ret:
    return ret

  return JsonResponse({'contents': result.clean_output()})


def job_update(request):
  if 'limit' not in request.GET:
    return HttpResponseBadRequest('Missing parameters')

  limit = int(request.GET['limit'])

  jobs_query = models.Job.objects.order_by('-last_modified')
  jobs = views.get_job_info(jobs_query, limit)

  return JsonResponse({'jobs': jobs})

def status_update(request):
  if 'last_request' not in request.GET:
    return HttpResponseBadRequest('Missing parameters')

  last_request = int(request.GET['last_request'])
  dt = timezone.localtime(timezone.now() - datetime.timedelta(seconds=last_request))
  repos_data = views.get_repos_status(dt)
  # we also need to check if a PR closed recently
  closed = []
  for pr in models.PullRequest.objects.filter(closed=True, last_modified__gte=dt).all():
    closed.append({'id': pr.pk})

  return JsonResponse({'repo_status': repos_data, 'closed': closed })

def job_results(request):
  if 'last_request' not in request.GET or 'job_id' not in request.GET:
    return HttpResponseBadRequest('Missing parameters')

  job_id = int(request.GET['job_id'])
  last_request = int(request.GET['last_request'])
  job = get_object_or_404(models.Job, pk=job_id)
  ret = can_see_results(request, job.recipe)
  if ret:
    return ret

  job_info = {
      'id': job.pk,
      'complete': job.complete,
      'status': job.status_slug(),
      'runtime': str(job.seconds),
      'ready': job.ready,
      'last_modified': views.display_time_str(job.last_modified),
      }

  dt = timezone.localtime(timezone.now() - datetime.timedelta(seconds=last_request))
  if job.last_modified < dt:
    return JsonResponse({'job_info': '', 'results': []})

  result_info = []

  for result in job.step_results.all():
    if result.last_modified < dt:
      continue
    exit_status = ''
    if result.complete:
      exit_status = result.exit_status
    info = {'id': result.id,
        'name': result.step.name,
        'runtime': str(result.seconds),
        'exit_status': exit_status,
        'output': result.clean_output(),
        'status': result.status_slug(),
        'running': result.status != models.JobStatus.NOT_STARTED,
        'complete': result.status_slug(),
        }
    result_info.append(info)

  return JsonResponse({'job_info': job_info, 'results': result_info})
