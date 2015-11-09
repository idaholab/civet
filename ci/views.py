from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.http import HttpResponse, Http404, HttpResponseNotAllowed, HttpResponseForbidden
from django.core.urlresolvers import reverse
from django.core.exceptions import PermissionDenied
from django.conf import settings
from django.db.models import Prefetch
from ci import models, event
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.contrib import messages
from datetime import timedelta
import time, os, tarfile, StringIO
from django.contrib.humanize.templatetags.humanize import naturaltime
from django.views.decorators.clickjacking import xframe_options_exempt

import logging, traceback
logger = logging.getLogger('ci')

def sortable_time_str(d):
  return d.strftime('%Y%m%d%H%M%S')

def display_time_str(d):
  #return d.strftime('%H:%M:%S %m/%d/%y')
  return naturaltime(d)

def get_repos_status(last_modified=None):
  """
  Get a list of open PRs, sorted by repository.
  """
  branch_q = models.Branch.objects.exclude(status=models.JobStatus.NOT_STARTED)
  if last_modified:
    branch_q = branch_q.filter(last_modified__gte=last_modified)
  branch_q = branch_q.order_by('name')

  pr_q = models.PullRequest.objects.filter(closed=False)
  if last_modified:
    pr_q = pr_q.filter(last_modified__gte=last_modified)
  pr_q = pr_q.order_by('number')

  repos = models.Repository.objects.order_by('name').prefetch_related(
      Prefetch('branches', queryset=branch_q, to_attr='active_branches')
      ).prefetch_related(Prefetch('pull_requests', queryset=pr_q, to_attr='open_prs')
      )
  if not repos:
    return []

  repos_data = []
  for repo in repos.all():
    branches = []
    for branch in repo.active_branches:
      branches.append({'id': branch.pk,
        'name': branch.name,
        'status': branch.status_slug(),
        'url': reverse('ci:view_branch', args=[branch.pk,]),
        'last_modified_date': sortable_time_str(branch.last_modified),
        })

    prs = []
    for pr in repo.open_prs:
      pr_event = pr.events.select_related('head__branch__repository__user').latest()
      username = pr_event.trigger_user
      if not username:
        username = pr_event.head.user().name

      prs.append({'id': pr.pk,
        'title': pr.title,
        'number': pr.number,
        'status': pr.status_slug(),
        'user': username,
        'url': reverse('ci:view_pr', args=[pr.pk,]),
        'last_modified_date': sortable_time_str(pr.last_modified),
        })

    if prs or branches:
      repos_data.append({'id': repo.pk,
        'name': repo.name,
        'branches': branches,
        'prs': prs,
        'url': reverse('ci:view_repo', args=[repo.pk,]),
        })

  return repos_data

def get_job_info(jobs, num):
  ret = []
  for job in jobs.order_by('-last_modified')[:num]:
    if job.event.pull_request:
      trigger = str(job.event.pull_request)
      trigger_url = reverse('ci:view_pr', args=[job.event.pull_request.pk])
    else:
      trigger = job.event.cause_str()
      trigger_url = reverse('ci:view_event', args=[job.event.pk])

    job_info = {
      'id': job.pk,
      'status': job.status_slug(),
      'runtime': str(job.seconds),
      'recipe_name': job.recipe.name,
      'job_url': reverse('ci:view_job', args=[job.pk,]),
      'config': job.config.name,
      'invalidated': job.invalidated,
      'trigger': trigger,
      'trigger_url': trigger_url,
      'repo': str(job.event.base.repo()),
      'user': str(job.event.head.user()),
      'last_modified': display_time_str(job.last_modified),
      'created': display_time_str(job.created),
      'last_modified_date': sortable_time_str(job.last_modified),
      'client_name': '',
      'client_url': '',
      }
    if job.client:
      job_info['client_name'] = job.client.name
      job_info['client_url'] = reverse('ci:view_client', args=[job.client.pk,])
    ret.append(job_info)
  return ret

def get_default_events_query(event_q=None):
  if not event_q:
    event_q = models.Event.objects
  return event_q.order_by('-created').select_related(
      'base__branch__repository__user__server', 'pull_request').prefetch_related('jobs__recipe', 'jobs__recipe__dependencies')

def main(request):
  """
  Main view. Just shows the status of repos, with open prs, as
  well as a short list of recent jobs.
  """
  repos = get_repos_status()
  events = get_default_events_query()[:30]
  return render( request,
      'ci/main.html',
      {'repos': repos,
        'recent_events': events,
        'last_request': int(time.time()),
        'event_limit': 30,
      })

def view_pr(request, pr_id):
  """
  Show the details of a PR
  """
  pr = get_object_or_404(models.PullRequest.objects.select_related('repository__user'), pk=pr_id)
  events = get_default_events_query(pr.events).select_related('head__branch__repository__user')
  return render(request, 'ci/pr.html', {'pr': pr, 'events': events})

def is_allowed_to_cancel(session, ev):
  ret_dict = {'user': None, 'allowed': False, 'error': None}
  try:
    auth = ev.base.server().auth()
    repo = ev.base.branch.repository
    user = auth.signed_in_user(repo.user.server, session)
    ret_dict['user'] = user
    if user:
      api = repo.user.server.api()
      auth_session = auth.start_session(session)
      if api.is_collaborator(auth_session, user, repo):
        ret_dict['allowed'] = True
      logger.info('User {} not a collaborator on {}'.format(user, repo))
  except Exception as e:
    ret_dict['error'] = str(e)

  return ret_dict

def job_permissions(session, job):
  """
  Logic for a job to see who can see results, activate,
  cancel, invalidate, or owns the job.
  """
  try:
    auth = job.event.base.server().auth()
    repo = job.recipe.repository
    user = auth.signed_in_user(repo.user.server, session)
    can_see_results = not job.recipe.private
    can_admin = False
    is_owner = False
    can_activate = False
    if user:
      if job.recipe.automatic == models.Recipe.AUTO_FOR_AUTHORIZED:
        if user in job.recipe.auto_authorized.all():
          can_activate = True

      api = repo.user.server.api()
      auth_session = auth.start_session_for_user(job.event.build_user)
      collab = api.is_collaborator(auth_session, user, repo)
      if collab:
        can_admin = True
        can_see_results = True
        is_owner = user == job.recipe.creator
        can_activate = True
    can_see_client = is_allowed_to_see_clients(session)

    return {'is_owner': is_owner,
        'can_see_results': can_see_results,
        'can_admin': can_admin,
        'can_activate': can_activate,
        'can_see_client': can_see_client,
        'error': None,
        }
  except Exception as e:
    # This can happen, for example, if there are DNS
    # timeouts
    return {'is_owner': False,
        'can_see_results': False,
        'can_admin': False,
        'can_activate': False,
        'can_see_client': False,
        'error': str(e),
        }

def view_event(request, event_id):
  """
  Show the details of an Event
  """
  ev = get_object_or_404(get_default_events_query().select_related('head__branch__repository__user'), pk=event_id)
  allowed = is_allowed_to_cancel(request.session, ev)
  if allowed['error']:
    messages.warning('Problem with cancel permissions: {}'.format(allowed['error']))
  return render(request, 'ci/event.html', {'event': ev, 'events': [ev], 'allowed_to_cancel': allowed['allowed']})

def get_job_results(request, job_id):
  """
  Just download all the output of the job into a tarball.
  """
  job = get_object_or_404(models.Job.objects.select_related('recipe',).prefetch_related('step_results'), pk=job_id)
  perms = job_permissions(request.session, job)
  if not perms['can_see_results']:
    return HttpResponseForbidden('Not allowed to see results')

  response = HttpResponse(content_type='application/x-gzip')
  base_name = 'results_{}_{}'.format(job.pk, job.recipe.name)
  response['Content-Disposition'] = 'attachment; filename="{}.tar.gz"'.format(base_name)
  tar = tarfile.open(fileobj=response, mode='w:gz')
  for result in job.step_results.all():
    info = tarfile.TarInfo(name='{}/{:02}_{}'.format(base_name, result.position, result.name))
    s = StringIO.StringIO(result.output.replace(u'\u2018', "'").replace(u"\u2019", "'"))
    info.size = len(s.buf)
    tar.addfile(tarinfo=info, fileobj=s)
  tar.close()
  return response

def view_job(request, job_id):
  """
  View the details of a job, along
  with any results.
  """
  job = get_object_or_404(models.Job.objects.select_related(
    'recipe__repository__user__server',
    'event__pull_request',
    'event__base__branch__repository__user__server',
    'event__head__branch__repository__user__server',
    'config',
    'client',
    ).prefetch_related('recipe__dependencies', 'recipe__auto_authorized', 'step_results'),
    pk=job_id)
  perms = job_permissions(request.session, job)
  if perms['error']:
    messages.warning('Problem with job permissions: {}'.format(perms['error']))

  perms['job'] = job
  return render(request, 'ci/job.html', perms)

def get_paginated(request, obj_list, obj_per_page=30):
  limit = request.GET.get('limit')
  if limit:
    obj_per_page = min(int(limit), 500)

  paginator = Paginator(obj_list, obj_per_page)

  page = request.GET.get('page')
  try:
    objs = paginator.page(page)
  except PageNotAnInteger:
    # If page is not an integer, deliver first page.
    objs = paginator.page(1)
  except EmptyPage:
    # If page is out of range (e.g. 9999), deliver last page of results.
    objs = paginator.page(paginator.num_pages)
  objs.limit = obj_per_page
  return objs

def view_repo(request, repo_id):
  """
  View details about a repository, along with
  some recent jobs for each branch.
  """
  repo = get_object_or_404(models.Repository.objects.select_related('user'), pk=repo_id)

  branch_info = []
  for branch in repo.branches.all():
    events = get_default_events_query().filter(base__branch=branch)[:30]
    if events.count() > 0:
      branch_info.append( {'branch': branch, 'events': events} )

  return render(request, 'ci/repo.html', {'repo': repo, 'branch_infos': branch_info})

def view_client(request, client_id):
  """
  View details about a client, along with
  some a list of paginated jobs it has run
  """
  client = get_object_or_404(models.Client, pk=client_id)

  allowed = is_allowed_to_see_clients(request.session)
  if not allowed:
    return render(request, 'ci/client.html', {'client': None, 'allowed': False})

  jobs_list = models.Job.objects.filter(client=client).order_by('-last_modified').select_related('config',
      'event__pull_request',
      'event__base__branch__repository__user',
      'event__head__branch__repository__user',
      'recipe',
      )
  jobs = get_paginated(request, jobs_list)
  return render(request, 'ci/client.html', {'client': client, 'jobs': jobs, 'allowed': True})

def view_branch(request, branch_id):
  branch = get_object_or_404(models.Branch, pk=branch_id)
  event_list = get_default_events_query().filter(base__branch=branch)
  events = get_paginated(request, event_list)
  return render(request, 'ci/branch.html', {'branch': branch, 'events': events})

def pr_list(request):
  pr_list = models.PullRequest.objects.order_by('-created').select_related('repository__user')
  prs = get_paginated(request, pr_list)
  return render(request, 'ci/prs.html', {'prs': prs})

def branch_list(request):
  branch_list = models.Branch.objects.exclude(status=models.JobStatus.NOT_STARTED).select_related('repository__user').order_by('repository')
  branches = get_paginated(request, branch_list)
  return render(request, 'ci/branches.html', {'branches': branches})

def is_allowed_to_see_clients(session):
  for server in settings.INSTALLED_GITSERVERS:
    gitserver = models.GitServer.objects.get(host_type=server)
    auth = gitserver.auth()
    user = auth.signed_in_user(gitserver, session)
    if not user:
      continue
    api = gitserver.api()
    auth_session = auth.start_session(session)
    for owner in settings.AUTHORIZED_OWNERS:
      repo_obj = models.Repository.objects.filter(user__name=owner, user__server=gitserver).first()
      if not repo_obj:
        continue
      if api.is_collaborator(auth_session, user, repo_obj):
        return True
  return False

def client_list(request):
  allowed = is_allowed_to_see_clients(request.session)
  if not allowed:
    return render(request, 'ci/clients.html', {'clients': None, 'allowed': False})

  client_list = models.Client.objects.order_by('name').all()
  clients = get_paginated(request, client_list)
  return render(request, 'ci/clients.html', {'clients': clients, 'allowed': True})

def event_list(request):
  event_list = get_default_events_query()
  events = get_paginated(request, event_list)
  return render(request, 'ci/events.html', {'events': events})

def recipe_events(request, recipe_id):
  recipe = get_object_or_404(models.Recipe, pk=recipe_id)
  event_list = get_default_events_query().filter(jobs__recipe=recipe)
  total = 0
  count = 0
  qs = models.Job.objects.filter(recipe=recipe)
  for job in qs.all():
    if job.status == models.JobStatus.SUCCESS:
      total += job.seconds.total_seconds()
      count += 1
  if count:
    total /= count
  events = get_paginated(request, event_list)
  avg = timedelta(seconds=total)
  return render(request, 'ci/recipe_events.html', {'recipe': recipe, 'events': events, 'average_time': avg })

def invalidate_job(request, job, same_client=False):
  job.complete = False
  job.invalidated = True
  job.same_client = same_client
  job.event.complete = False
  job.seconds = timedelta(seconds=0)
  if not same_client:
    job.client = None
  job.active = True
  job.status = models.JobStatus.NOT_STARTED
  job.step_results.all().delete()
  job.save()
  event.make_jobs_ready(job.event)
  messages.info(request, 'Job results invalidated for {}'.format(job))

def invalidate_event(request, event_id):
  """
  Invalidate all the jobs of an event.
  The user must be signed in.
  """
  if request.method != 'POST':
    return HttpResponseNotAllowed(['POST'])

  ev = get_object_or_404(models.Event, pk=event_id)
  allowed = is_allowed_to_cancel(request.session, ev)
  if not allowed['allowed']:
    raise PermissionDenied('You need to be signed in to invalidate results.')

  logger.info('Event {} invalidated by {}'.format(ev, allowed['user']))
  same_client = request.POST.get('same_client') == "on"
  for job in ev.jobs.all():
    invalidate_job(request, job, same_client)
  ev.complete = False
  ev.status = models.JobStatus.NOT_STARTED
  ev.save()

  return redirect('ci:view_event', event_id=ev.pk)

def invalidate(request, job_id):
  """
  Invalidate the results of a Job.
  The user must be signed in.
  """
  if request.method != 'POST':
    return HttpResponseNotAllowed(['POST'])

  job = get_object_or_404(models.Job, pk=job_id)
  allowed = is_allowed_to_cancel(request.session, job.event)
  if not allowed['allowed']:
    raise PermissionDenied('You are not allowed to invalidate results.')
  same_client = request.POST.get('same_client') == 'on'

  logger.info('Job {} on {} invalidated by {}'.format(job, job.recipe.repository, allowed['user']))
  invalidate_job(request, job, same_client)
  return redirect('ci:view_job', job_id=job.pk)

def sort_recipes_key(entry):
  return str(entry[0].repository)

def view_profile(request, server_type):
  """
  View the user's profile.
  """
  server = get_object_or_404(models.GitServer, host_type=server_type)
  auth = server.auth()
  user = auth.signed_in_user(server, request.session)
  api = server.api()
  if not user:
    request.session['source_url'] = request.build_absolute_uri()
    return redirect(server.api().sign_in_url())

  auth_session = auth.start_session(request.session)
  repos = api.get_repos(auth_session, request.session)
  org_repos = api.get_org_repos(auth_session, request.session)
  recipes = models.Recipe.objects.filter(creator=user).order_by('repository', 'cause', 'name')\
      .select_related('branch', 'repository__user')\
      .prefetch_related('build_configs', 'dependencies')
  recipe_data =[]
  prev_repo = 0
  current_data = []
  for recipe in recipes.all():
    if recipe.repository.pk != prev_repo:
      prev_repo = recipe.repository.pk
      if current_data:
        recipe_data.append(current_data)
      current_data = [recipe]
    else:
      current_data.append(recipe)
  if current_data:
    recipe_data.append(current_data)
  recipe_data.sort(key=sort_recipes_key)

  events = get_default_events_query().filter(build_user=user)[:30]
  return render(request, 'ci/profile.html', {
    'user': user,
    'repos': repos,
    'org_repos': org_repos,
    'recipes_by_repo': recipe_data,
    'events': events,
    })


@csrf_exempt
def manual_branch(request, build_key, branch_id):
  """
  Endpoint for creating a manual event.
  """
  if request.method != 'POST':
    return HttpResponseNotAllowed(['POST'])

  branch = get_object_or_404(models.Branch, pk=branch_id)
  user = get_object_or_404(models.GitUser, build_key=build_key)
  reply = 'OK'
  try:
    logger.info('Running manual with user %s on branch %s' % (user, branch))
    oauth_session = user.start_session()
    latest = user.api().last_sha(oauth_session, branch.repository.user.name, branch.repository.name, branch.name)
    if latest:
      mev = event.ManualEvent(user, branch, latest)
      mev.save(request)
      reply = 'Success. Scheduled recipes on branch %s for user %s' % (branch, user)
      messages.info(request, reply)
  except Exception as e:
    reply = 'Error running manual for build_key %s on branch %s\nError: %s'\
        % (build_key, branch, traceback.format_exc(e))
    messages.error(request, reply)

  logger.info(reply)
  next_url = request.POST.get('next', None)
  if next_url:
    return redirect(next_url)
  return HttpResponse(reply)

def activate_job(request, job_id):
  """
  Endpoint for creating a manual event.
  """
  if request.method != 'POST':
    return HttpResponseNotAllowed(['POST'])

  job = get_object_or_404(models.Job, pk=job_id)
  owner = job.recipe.repository.user
  auth = owner.server.auth()
  user = auth.signed_in_user(owner.server, request.session)
  if not user:
    raise PermissionDenied('You need to be signed in to activate a job')

  auth_session = auth.start_session(request.session)
  if owner.server.api().is_collaborator(auth_session, user, job.recipe.repository):
    job.active = True
    job.status = models.JobStatus.NOT_STARTED
    job.event.status = models.JobStatus.NOT_STARTED
    job.event.complete = False
    job.event.save()
    job.save()
    event.make_jobs_ready(job.event)
    messages.info(request, 'Job activated')
  else:
    raise PermissionDenied('%s is not a collaborator on %s' % (user, job.recipe.repository))

  return redirect('ci:view_job', job_id=job.pk)


def cancel_event(request, event_id):
  if request.method != 'POST':
    return HttpResponseNotAllowed(['POST'])

  ev = get_object_or_404(models.Event, pk=event_id)
  allowed= is_allowed_to_cancel(request.session, ev)

  if allowed['allowed']:
    event.cancel_event(ev)
    logger.info('Event {} canceled by {}'.format(ev, allowed['user']))
    messages.info(request, 'Event {} canceled'.format(ev))
  else:
    return HttpResponseForbidden('Not allowed to cancel this event')

  return redirect('ci:view_event', event_id=ev.pk)

def cancel_job(request, job_id):
  if request.method != 'POST':
    return HttpResponseNotAllowed(['POST'])

  job = get_object_or_404(models.Job, pk=job_id)
  allowed = is_allowed_to_cancel(request.session, job.event)
  if allowed['allowed']:
    job.status = models.JobStatus.CANCELED
    job.complete = True
    job.save()
    job.event.status = models.JobStatus.CANCELED
    job.event.save()
    logger.info('Job {} on {} canceled by {}'.format(job, job.recipe.repository, allowed['user']))
    messages.info(request, 'Job {} canceled'.format(job))
  else:
    return HttpResponseForbidden('Not allowed to cancel this job')
  return redirect('ci:view_job', job_id=job.pk)


def start_session_by_name(request, name):
  if not settings.DEBUG:
    raise Http404()

  user = get_object_or_404(models.GitUser, name=name)
  if not user.token:
    raise Http404('User %s does not have a token.' % user.name )
  user.server.auth().set_browser_session_from_user(request.session, user)
  messages.info(request, "Started session")
  return redirect('ci:main')

def start_session(request, user_id):
  if not settings.DEBUG:
    raise Http404()

  user = get_object_or_404(models.GitUser, pk=user_id)
  if not user.token:
    raise Http404('User %s does not have a token.' % user.name )
  user.server.auth().set_browser_session_from_user(request.session, user)
  messages.info(request, "Started session")
  return redirect('ci:main')


def read_recipe_file(filename):
  fname = '{}/{}'.format(settings.RECIPE_BASE_DIR, filename)
  if not os.path.exists(fname):
    return None
  with open(fname, 'r') as f:
    return f.read()

def get_config_module(config):
  config_map = {'linux-gnu': 'moose-dev-gcc',
    'linux-clang': 'moose-dev-clang',
    'linux-valgrind': 'moose-dev-gcc',
    'linux-gnu-coverage': 'moose-dev-gcc',
    'linux-intel': 'moose-dev-intel',
    'linux-gnu-timing': 'moose-dev-gcc',
    }
  mod = config_map.get(config)
  if not mod:
    mod = 'moose-dev-gcc'
  return mod

def job_script(request, job_id):
  job = get_object_or_404(models.Job, pk=job_id)
  perms = job_permissions(request.session, job)
  if not perms['is_owner']:
    raise Http404('Not the owner')
  script = '<pre>#!/bin/bash'
  script += '\n# Script for job {}'.format(job)
  script += '\n# Note that BUILD_ROOT and other environment variables set by the client are not set'
  script += '\n# It is a good idea to redirect stdin, id "./script.sh  < /dev/null"'
  script += '\n\n'
  script += '\nmodule purge'
  mod = get_config_module(job.config.name)
  script += '\nmodule load {}\n'.format(mod)

  script += '\nexport BUILD_ROOT=""'
  script += '\nexport MOOSE_JOBS="1"'
  script += '\n\n'
  recipe = job.recipe
  for prestep in recipe.prestepsources.all():
    script += '\n{}\n'.format(read_recipe_file(prestep.filename))

  for env in recipe.environment_vars.all():
    script += '\nexport {}={}'.format(env.name, env.value)

  script += '\nexport recipe_name="{}"'.format(job.recipe.name)
  script += '\nexport job_id="{}"'.format(job.pk)
  script += '\nexport abort_on_failure="{}"'.format(job.recipe.abort_on_failure)
  script += '\nexport recipe_id="{}"'.format(job.recipe.pk)
  script += '\nexport comments_url="{}"'.format(job.event.comments_url)
  script += '\nexport base_repo="{}"'.format(job.event.base.repo())
  script += '\nexport base_ref="{}"'.format(job.event.base.branch.name)
  script += '\nexport base_sha="{}"'.format(job.event.base.sha)
  script += '\nexport base_ssh_url="{}"'.format(job.event.base.ssh_url)
  script += '\nexport head_repo="{}"'.format(job.event.head.repo())
  script += '\nexport head_ref="{}"'.format(job.event.head.branch.name)
  script += '\nexport head_sha="{}"'.format(job.event.head.sha)
  script += '\nexport head_ssh_url="{}"'.format(job.event.head.ssh_url)
  script += '\nexport cause="{}"'.format(job.recipe.cause_str())
  script += '\nexport config="{}"'.format(job.config.name)
  script += '\n\n'

  count = 0
  step_cmds = ''
  for step in recipe.steps.order_by('position').all():
    script += '\nfunction step_{}\n{{'.format(count)
    script += '\n\tlocal step_num="{}"'.format(step.position)
    script += '\n\tlocal step_position="{}"'.format(step.position)
    script += '\n\tlocal step_name="{}"'.format(step.name)
    script += '\n\tlocal step_id="{}"'.format(step.pk)
    script += '\n\tlocal step_abort_on_failure="{}"'.format(step.abort_on_failure)

    for env in step.step_environment.all():
      script += '\n\tlocal {}="{}"'.format(env.name, env.value)

    for l in read_recipe_file(step.filename).split('\n'):
      script += '\n\t{}'.format(l.replace('exit 0', 'return 0'))
    script += '\n}\n'
    step_cmds += '\nstep_{}'.format(count)
    count += 1

  script += step_cmds
  script += '</pre>'
  return HttpResponse(script)

@xframe_options_exempt
def mooseframework(request):
  message = ''
  data = None
  try:
    repo = models.Repository.objects.get(
        user__name='idaholab',
        name='moose',
        user__server__host_type=settings.GITSERVER_GITHUB
        )
  except models.Repository.DoesNotExist:
    return HttpResponse('Moose not available')

  try:
    master = repo.branches.get(name='master')
    devel = repo.branches.get(name='devel')
  except models.Branch.DoesNotExist:
    return HttpResponse('Branches not there')

  data = {'master_status': master.status_slug()}
  data['master_url'] = request.build_absolute_uri(reverse('ci:view_branch', args=[master.pk,]))
  data['devel_status'] = devel.status_slug()
  data['devel_url'] = request.build_absolute_uri(reverse('ci:view_branch', args=[devel.pk,]))
  prs = models.PullRequest.objects.filter(repository=repo, closed=False).order_by('number')
  pr_data = []
  for pr in prs:
    d = {'number': pr.number,
        'url': request.build_absolute_uri(reverse('ci:view_pr', args=[pr.pk,])),
        'status': pr.status_slug(),
        }
    pr_data.append(d)
  data['prs'] = pr_data

  return render(request,
      'ci/mooseframework.html',
      {'status': data,
        'message': message,
      })

def scheduled_events(request):
  """
  List schedule events
  """
  event_list = get_default_events_query().filter(cause=models.Event.MANUAL)
  events = get_paginated(request, event_list)
  return render(request, 'ci/scheduled.html', {'events': events})
