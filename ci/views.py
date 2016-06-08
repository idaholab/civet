from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.http import HttpResponse, HttpResponseNotAllowed, HttpResponseForbidden
from django.core.urlresolvers import reverse
from django.core.exceptions import PermissionDenied
from django.conf import settings
from django.db.models import Prefetch
from ci import models, event, forms
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.contrib import messages
from datetime import timedelta
import time, tarfile, StringIO
from django.utils.html import escape
import TimeUtils
import Permissions

import logging, traceback
logger = logging.getLogger('ci')

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
        'last_modified_date': TimeUtils.sortable_time_str(branch.last_modified),
        })

    prs = []
    for pr in repo.open_prs:
      pr_event = pr.events.select_related('head__branch__repository__user').latest()
      username = pr_event.trigger_user
      if not username:
        username = pr_event.head.user().name

      prs.append({'id': pr.pk,
        'title': escape(pr.title),
        'number': pr.number,
        'status': pr.status_slug(),
        'user': username,
        'url': reverse('ci:view_pr', args=[pr.pk,]),
        'last_modified_date': TimeUtils.sortable_time_str(pr.last_modified),
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
      'last_modified': TimeUtils.display_time_str(job.last_modified),
      'created': TimeUtils.display_time_str(job.created),
      'last_modified_date': TimeUtils.sortable_time_str(job.last_modified),
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
      'base__branch__repository__user__server', 'pull_request').prefetch_related('jobs__recipe', 'jobs__recipe__depends_on')

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
  Input:
    request: django.http.HttpRequest
    pr_id: pk of models.PullRequest
  Return:
    django.http.HttpResponse based object
  """
  pr = get_object_or_404(models.PullRequest.objects.select_related('repository__user'), pk=pr_id)
  events = get_default_events_query(pr.events).select_related('head__branch__repository__user')
  allowed, signed_in_user = Permissions.is_allowed_to_cancel(request.session, events.first())
  if allowed:
    alt_recipes = models.Recipe.objects.filter(repository=pr.repository, build_user=pr.events.latest().build_user, current=True, cause=models.Recipe.CAUSE_PULL_REQUEST_ALT).order_by("display_name")
    current_alt = [ r.pk for r in pr.alternate_recipes.all() ]
    choices = [ (r.pk, r.display_name) for r in alt_recipes ]
    if choices:
      if request.method == "GET":
        form = forms.AlternateRecipesForm()
        form.fields["recipes"].choices = choices
        form.fields["recipes"].initial = current_alt
      else:
        form = forms.AlternateRecipesForm(request.POST)
        form.fields["recipes"].choices = choices
        if form.is_valid():
          pr.alternate_recipes.clear()
          for pk in form.cleaned_data["recipes"]:
            alt = models.Recipe.objects.get(pk=pk)
            pr.alternate_recipes.add(alt)
          # do some saves to update the timestamp so that the javascript updater gets activated
          pr.save()
          pr.events.latest().save()
          messages.info(request, "Success")
          pr_event = event.PullRequestEvent()
          pr_event.create_pr_alternates(request, pr)
    else:
      form = None
  else:
    form = None

  return render(request, 'ci/pr.html', {'pr': pr, 'events': events, "form": form, "allowed": allowed})

def view_event(request, event_id):
  """
  Show the details of an Event
  """
  ev = get_object_or_404(get_default_events_query().select_related('head__branch__repository__user'), pk=event_id)
  allowed, signed_in_user = Permissions.is_allowed_to_cancel(request.session, ev)
  return render(request, 'ci/event.html', {'event': ev, 'events': [ev], 'allowed_to_cancel': allowed})

def get_job_results(request, job_id):
  """
  Just download all the output of the job into a tarball.
  """
  job = get_object_or_404(models.Job.objects.select_related('recipe',).prefetch_related('step_results'), pk=job_id)
  perms = Permissions.job_permissions(request.session, job)
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
    'recipe__build_user__server',
    'event__pull_request',
    'event__base__branch__repository__user__server',
    'event__head__branch__repository__user__server',
    'config',
    'client',
    ).prefetch_related('recipe__depends_on', 'recipe__auto_authorized', 'step_results'),
    pk=job_id)
  perms = Permissions.job_permissions(request.session, job)

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
  copy_get = request.GET.copy()
  if copy_get.get('page'):
    del copy_get['page']
  copy_get['limit'] = obj_per_page
  objs.get_params = copy_get.urlencode()
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

  allowed = Permissions.is_allowed_to_see_clients(request.session)
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

def client_list(request):
  allowed = Permissions.is_allowed_to_see_clients(request.session)
  if not allowed:
    return render(request, 'ci/clients.html', {'clients': None, 'allowed': False})

  client_list = models.Client.objects.order_by('name').all()
  return render(request, 'ci/clients.html', {'clients': client_list, 'allowed': True})

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

def set_job_invalidated(job, same_client=False):
  """
  Set the job as invalidated.
  Separated out for easier testing
  Input:
    job: models.Job to be invalidated
    same_client: bool: If True then the job will only run on the same client
  """
  old_recipe = job.recipe
  job.complete = False
  latest_recipe = models.Recipe.objects.filter(filename=job.recipe.filename, current=True, cause=job.recipe.cause).order_by('-created')
  if latest_recipe.count():
    job.recipe = latest_recipe.first()
  job.invalidated = True
  job.same_client = same_client
  job.seconds = timedelta(seconds=0)
  if not same_client:
    job.client = None
  job.active = True
  job.status = models.JobStatus.NOT_STARTED
  job.step_results.all().delete()
  job.save()
  job.event.complete = False
  job.event.status = event.event_status(job.event)
  job.event.save()
  event.make_jobs_ready(job.event)
  if old_recipe.jobs.count() == 0:
    old_recipe.delete()

def invalidate_job(request, job, same_client=False):
  """
  Convience function to invalidate a job and show a message to the user.
  Input:
    request: django.http.HttpRequest
    job. models.Job
    same_client: bool
  """
  set_job_invalidated(job, same_client)
  messages.info(request, 'Job results invalidated for {}'.format(job))

def invalidate_event(request, event_id):
  """
  Invalidate all the jobs of an event.
  The user must be signed in.
  Input:
    request: django.http.HttpRequest
    event_id. models.Event.pk: PK of the event to be invalidated
  Return: django.http.HttpResponse based object
  """
  if request.method != 'POST':
    return HttpResponseNotAllowed(['POST'])

  ev = get_object_or_404(models.Event, pk=event_id)
  allowed, signed_in_user = Permissions.is_allowed_to_cancel(request.session, ev)
  if not allowed:
    raise PermissionDenied('You need to be signed in and be a collaborator to invalidate results.')

  logger.info('Event {}: {} invalidated by {}'.format(ev.pk, ev, signed_in_user))
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
  Input:
    request: django.http.HttpRequest
    job_id: models.Job.pk
  """
  if request.method != 'POST':
    return HttpResponseNotAllowed(['POST'])

  job = get_object_or_404(models.Job, pk=job_id)
  allowed, signed_in_user = Permissions.is_allowed_to_cancel(request.session, job.event)
  if not allowed:
    raise PermissionDenied('You are not allowed to invalidate results.')
  same_client = request.POST.get('same_client') == 'on'

  logger.info('Job {}: {} on {} invalidated by {}'.format(job.pk, job, job.recipe.repository, signed_in_user))
  invalidate_job(request, job, same_client)
  return redirect('ci:view_job', job_id=job.pk)

def sort_recipes_key(entry):
  return str(entry[0].repository)

def view_profile(request, server_type):
  """
  View the recipes that the user owns
  """
  server = get_object_or_404(models.GitServer, host_type=server_type)
  auth = server.auth()
  user = auth.signed_in_user(server, request.session)
  if not user:
    request.session['source_url'] = request.build_absolute_uri()
    return redirect(server.api().sign_in_url())

  recipes = models.Recipe.objects.filter(build_user=user, current=True).order_by('repository', 'cause', 'branch__name', 'name')\
      .select_related('branch', 'repository__user')\
      .prefetch_related('build_configs', 'depends_on')
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

  return render(request, 'ci/profile.html', {
    'user': user,
    'recipes_by_repo': recipe_data,
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

  collab, user = Permissions.is_collaborator(auth, request.session, job.event.build_user, job.recipe.repository, user=user)
  if collab:
    job.active = True
    job.ready = True
    job.status = models.JobStatus.NOT_STARTED
    job.event.status = models.JobStatus.NOT_STARTED
    job.event.complete = False
    job.event.save()
    job.save()
    messages.info(request, 'Job activated')
  else:
    raise PermissionDenied('Activate job: {} is NOT a collaborator on {}'.format(user, job.recipe.repository))

  return redirect('ci:view_job', job_id=job.pk)

def cancel_event(request, event_id):
  if request.method != 'POST':
    return HttpResponseNotAllowed(['POST'])

  ev = get_object_or_404(models.Event, pk=event_id)
  allowed, signed_in_user = Permissions.is_allowed_to_cancel(request.session, ev)

  if allowed:
    event.cancel_event(ev)
    logger.info('Event {}: {} canceled by {}'.format(ev.pk, ev, signed_in_user))
    messages.info(request, 'Event {} canceled'.format(ev))
  else:
    return HttpResponseForbidden('Not allowed to cancel this event')

  return redirect('ci:view_event', event_id=ev.pk)

def cancel_job(request, job_id):
  if request.method != 'POST':
    return HttpResponseNotAllowed(['POST'])

  job = get_object_or_404(models.Job, pk=job_id)
  allowed, signed_in_user = Permissions.is_allowed_to_cancel(request.session, job.event)
  if allowed:
    job.status = models.JobStatus.CANCELED
    job.complete = True
    job.save()
    job.event.status = models.JobStatus.CANCELED
    job.event.save()
    logger.info('Job {}: {} on {} canceled by {}'.format(job.pk, job, job.recipe.repository, signed_in_user))
    messages.info(request, 'Job {} canceled'.format(job))
  else:
    return HttpResponseForbidden('Not allowed to cancel this job')
  return redirect('ci:view_job', job_id=job.pk)

def mooseframework(request):
  """
  This produces a very basic set of status reports for MOOSE, its branches and
  its open PRs.
  Intended to be included on mooseframework.org
  """
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

def job_info_search(request):
  """
  Presents a form to filter jobs by either OS version or modules loaded.
  The modules loaded are parsed from the output of jobs and then stored
  in the database. This form allows to select which jobs contained the
  selected modules.
  Input:
    request: django.http.HttpRequest
  Return: django.http.HttpResponse based object
  """
  jobs = []
  if request.method == "GET":
    form = forms.JobInfoForm(request.GET)
    if form.is_valid():
      jobs = models.Job.objects.order_by("-created").select_related("event",
          "recipe",
          'config',
          'event__pull_request',
          'event__base__branch__repository__user',
          'event__head__branch__repository__user')
      if form.cleaned_data['os_versions']:
        jobs = jobs.filter(operating_system__in=form.cleaned_data['os_versions'])
      if form.cleaned_data['modules']:
        for mod in form.cleaned_data['modules'].all():
          jobs = jobs.filter(loaded_modules__pk=mod.pk)

  jobs = get_paginated(request, jobs)
  return render(request, 'ci/job_info_search.html', {"form": form, "jobs": jobs})
