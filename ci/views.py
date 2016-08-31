
# Copyright 2016 Battelle Energy Alliance, LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.http import HttpResponse, HttpResponseNotAllowed, HttpResponseForbidden
from django.core.urlresolvers import reverse
from django.core.exceptions import PermissionDenied
from django.conf import settings
from ci import models, event, forms
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.contrib import messages
from datetime import timedelta
import tarfile, StringIO
import RepositoryStatus, EventsStatus, Permissions, PullRequestEvent, ManualEvent, TimeUtils
from django.utils.html import escape

import logging, traceback
logger = logging.getLogger('ci')

def get_user_repos_info(request, limit=30, last_modified=None):
  """
  Get the information for the main view.
  This checks to see if the user has preferred repositories set, and if
  so then just shows those.
  You can also set the "default" parameter to show all the repositories.
  Input:
    request: django.http.HttpRequest
    limit: int: How many events to show
    last_modified: datetime: If not None, then only get information that has occured after this time.
  Return:
    (repo_info, evs_info, default):
      repo_info: list of dicts of repository status
      evs_info: list of dicts of event information
      default: Whether the default view was enforced
  """
  pks = []
  default = request.GET.get('default')
  if default is None:
    default = False
    for server in settings.INSTALLED_GITSERVERS:
      gitserver = models.GitServer.objects.get(host_type=server)
      auth = gitserver.auth()
      user = auth.signed_in_user(gitserver, request.session)
      if user != None:
        for repo in user.preferred_repos.all():
          pks.append(repo.pk)
  else:
    default = True
  if pks:
    repos = RepositoryStatus.filter_repos_status(pks, last_modified=last_modified)
    evs_info = EventsStatus.events_filter_by_repo(pks, limit=limit, last_modified=last_modified)
  else:
    repos = RepositoryStatus.main_repos_status(last_modified=last_modified)
    evs_info = EventsStatus.all_events_info(limit=limit, last_modified=last_modified)
  return repos, evs_info, default

def main(request):
  """
  Main view. Just shows the status of repos, with open prs, as
  well as a short list of recent jobs.
  Input:
    request: django.http.HttpRequest
  Return:
    django.http.HttpResponse based object
  """
  limit = 30
  repos, evs_info, default = get_user_repos_info(request, limit=limit)
  return render(request,
      'ci/main.html',
      {'repos': repos,
        'recent_events': evs_info,
        'last_request': TimeUtils.get_local_timestamp(),
        'event_limit': limit,
        'update_interval': settings.HOME_PAGE_UPDATE_INTERVAL,
        'default_view': default,
      })

def user_repo_settings(request):
  """
  Allow the user to change the default view on the main page.
  Input:
    request: django.http.HttpRequest
  Return:
    django.http.HttpResponse based object
  """
  current_repos = []
  all_repos = []
  users = {}
  for server in settings.INSTALLED_GITSERVERS:
    gitserver = models.GitServer.objects.get(host_type=server)
    auth = gitserver.auth()
    user = auth.signed_in_user(gitserver, request.session)
    if user != None:
      users[gitserver.pk] = user
      for repo in user.preferred_repos.all():
        current_repos.append(repo.pk)
    for repo in models.Repository.objects.filter(active=True).order_by('user__name', 'name').all():
      all_repos.append((repo.pk, str(repo)))

  if not users:
    messages.error(request, "You need to be signed in to set preferences")
    return render(request, 'ci/repo_settings.html', {"form": None})

  if request.method == "GET":
    form = forms.UserRepositorySettingsForm()
    form.fields["repositories"].choices = all_repos
    form.fields["repositories"].initial = current_repos
  else:
    form = forms.UserRepositorySettingsForm(request.POST)
    form.fields["repositories"].choices = all_repos
    if form.is_valid():
      for server, user in users.items():
        messages.info(request, "Set repository preferences for %s" % user)
        user.preferred_repos.clear()

      for pk in form.cleaned_data["repositories"]:
        repo = models.Repository.objects.get(pk=pk)
        user = users[repo.server().pk]
        user.preferred_repos.add(repo)

  return render(request, 'ci/repo_settings.html', {"form": form})

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
  ev = pr.events.select_related('build_user', 'base__branch__repository__user__server').latest()
  allowed, signed_in_user = Permissions.is_allowed_to_cancel(request.session, ev)
  if allowed:
    alt_recipes = models.Recipe.objects.filter(repository=pr.repository, build_user=ev.build_user, current=True, cause=models.Recipe.CAUSE_PULL_REQUEST_ALT).order_by("display_name")
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
          pr.events.latest('created').save()
          messages.info(request, "Success")
          pr_event = PullRequestEvent.PullRequestEvent()
          pr_event.create_pr_alternates(request, pr)
    else:
      form = None
  else:
    form = None

  events = EventsStatus.events_with_head(pr.events)
  evs_info = EventsStatus.events_info(events, events_url=True)
  return render(request, 'ci/pr.html', {'pr': pr, 'events': evs_info, "form": form, "allowed": allowed, "update_interval": settings.EVENT_PAGE_UPDATE_INTERVAL})

def view_event(request, event_id):
  """
  Show the details of an Event
  """
  ev = get_object_or_404(EventsStatus.events_with_head(), pk=event_id)
  evs_info = EventsStatus.events_info([ev])
  allowed, signed_in_user = Permissions.is_allowed_to_cancel(request.session, ev)
  return render(request, 'ci/event.html', {'event': ev, 'events': evs_info, 'allowed_to_cancel': allowed, "update_interval": settings.EVENT_PAGE_UPDATE_INTERVAL})

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
    s = StringIO.StringIO(result.plain_output().replace(u'\u2018', "'").replace(u"\u2019", "'"))
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
  clients = None
  if perms['can_see_client']:
    clients = models.Client.objects.exclude(status=models.Client.DOWN).order_by("name").all()
  perms['job'] = job
  perms['clients'] = clients
  perms['update_interval'] = settings.JOB_PAGE_UPDATE_INTERVAL
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
  This has the same layout as the main page but only for single repository.
  """
  repo = get_object_or_404(models.Repository.objects.select_related('user__server'), pk=repo_id)

  limit = 30
  repos_status = RepositoryStatus.filter_repos_status([repo.pk])
  events_info = EventsStatus.events_filter_by_repo([repo.pk], limit=limit)

  params = {
      'repo': repo,
      'repos_status': repos_status,
      'events_info': events_info,
      'event_limit': limit,
      'last_request': TimeUtils.get_local_timestamp(),
      'update_interval': settings.HOME_PAGE_UPDATE_INTERVAL
      }
  return render(request, 'ci/repo.html', params)

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
  branch = get_object_or_404(models.Branch.objects.select_related("repository__user__server"), pk=branch_id)
  event_list = EventsStatus.get_default_events_query().filter(base__branch=branch)
  events = get_paginated(request, event_list)
  evs_info = EventsStatus.events_info(events)
  return render(request, 'ci/branch.html', {'branch': branch, 'events': evs_info, 'pages': events})

def pr_list(request):
  pr_list = models.PullRequest.objects.order_by('-created').select_related('repository__user__server').order_by('repository__user__name', 'repository__name', 'number')
  prs = get_paginated(request, pr_list)
  return render(request, 'ci/prs.html', {'prs': prs})

def branch_list(request):
  branch_list = models.Branch.objects.exclude(status=models.JobStatus.NOT_STARTED).select_related('repository__user__server').order_by('repository__user__name', 'repository__name', 'name')
  branches = get_paginated(request, branch_list)
  return render(request, 'ci/branches.html', {'branches': branches})

def client_list(request):
  allowed = Permissions.is_allowed_to_see_clients(request.session)
  if not allowed:
    return render(request, 'ci/clients.html', {'clients': None, 'allowed': False})

  client_list = clients_info()
  return render(request, 'ci/clients.html', {'clients': client_list, 'allowed': True, 'update_interval': settings.HOME_PAGE_UPDATE_INTERVAL,})

def clients_info():
  """
  Gets the information on all the clients.
  Retunrns:
    list of dicts containing client information
  """
  client_list = models.Client.objects.order_by('name')
  clients = []
  for c in client_list.all():
    d = {'pk': c.pk,
        "ip": c.ip,
        "name": c.name,
        "message": c.status_message,
        "status": c.status_str(),
        "lastseen": TimeUtils.human_time_str(c.last_seen),
        }
    if c.status != models.Client.DOWN and c.unseen_seconds() > 60:
      d["status_class"] = "client_NotSeen"
    else:
      d["status_class"] = "client_%s" % c.status_slug()
    clients.append(d)
  return clients

def event_list(request):
  event_list = EventsStatus.get_default_events_query()
  events = get_paginated(request, event_list)
  evs_info = EventsStatus.events_info(events)
  return render(request, 'ci/events.html', {'events': evs_info, 'pages': events})

def recipe_events(request, recipe_id):
  recipe = get_object_or_404(models.Recipe, pk=recipe_id)
  event_list = EventsStatus.get_default_events_query().filter(jobs__recipe__filename=recipe.filename, jobs__recipe__cause=recipe.cause)
  total = 0
  count = 0
  qs = models.Job.objects.filter(recipe__filename=recipe.filename)
  for job in qs.all():
    if job.status == models.JobStatus.SUCCESS:
      total += job.seconds.total_seconds()
      count += 1
  if count:
    total /= count
  events = get_paginated(request, event_list)
  evs_info = EventsStatus.events_info(events)
  avg = timedelta(seconds=total)
  return render(request, 'ci/recipe_events.html', {'recipe': recipe, 'events': evs_info, 'average_time': avg, 'pages': events })

def set_job_invalidated(job, message, same_client=False, client=None):
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
  if client:
    job.client = client
  elif not same_client:
    job.client = None
  job.active = True
  job.status = models.JobStatus.NOT_STARTED
  job.step_results.all().delete()
  job.failed_step = ""
  job.save()
  job.event.complete = False
  job.event.status = event.event_status(job.event)
  job.event.save()
  models.JobChangeLog.objects.create(job=job, message=message)
  event.make_jobs_ready(job.event)
  if old_recipe.jobs.count() == 0:
    old_recipe.delete()

def invalidate_job(request, job, message, same_client=False, client=None):
  """
  Convience function to invalidate a job and show a message to the user.
  Input:
    request: django.http.HttpRequest
    job. models.Job
    same_client: bool
  """
  set_job_invalidated(job, message, same_client, client)
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
    messages.error(request, 'You need to be signed in and be a collaborator to invalidate results.')
    return redirect('ci:view_event', event_id=ev.pk)

  comment = escape(request.POST.get("comment"))
  logger.info('Event {}: {} invalidated by {}'.format(ev.pk, ev, signed_in_user))
  event_url = reverse("ci:view_event", args=[ev.pk])
  message = "Parent <a href='%s'>event</a> invalidated by %s" % (event_url, signed_in_user)
  if comment:
    message += " with comment: %s" % comment

  post_to_pr = request.POST.get("post_to_pr") == "on"
  if post_to_pr:
    post_event_change_to_pr(ev, "invalidated", comment, signed_in_user)

  same_client = request.POST.get('same_client') == "on"
  for job in ev.jobs.all():
    invalidate_job(request, job, message, same_client)
  ev.complete = False
  ev.status = models.JobStatus.NOT_STARTED
  ev.save()

  return redirect('ci:view_event', event_id=ev.pk)

def post_job_change_to_pr(job, action, comment, signed_in_user):
  """
  Makes a PR comment to notify of a change in job status.
  Input:
    job: models.Job: Job that has changed
    action: str: Describing what happend (like "canceled" or "invalidated")
    comment: str: Comment that was entered in by the user
    signed_in_user: models.GitUser: the initiating user
  """
  if job.event.pull_request and job.event.comments_url:
    auth = job.event.build_user.start_session()
    gapi = job.event.base.server().api()
    additional = ""
    if comment:
      additional = "\n\n%s" % comment
    pr_message = "Job `%s` on %s : %s by @%s%s" % (job, job.event.head.sha[:7], action, signed_in_user, additional)
    gapi.pr_comment(auth, job.event.comments_url, pr_message)

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
  selected_client = request.POST.get('client_list')
  comment = escape(request.POST.get('comment'))
  post_to_pr = request.POST.get('post_to_pr') == 'on'
  client = None
  if selected_client:
    try:
      client = models.Client.objects.get(pk=int(selected_client))
      same_client = True
    except:
      pass
  message = "Invalidated by %s" % signed_in_user
  if comment:
    message += "\nwith comment: %s" % comment

  if post_to_pr:
    post_job_change_to_pr(job, "invalidated", comment, signed_in_user)

  logger.info('Job {}: {} on {} invalidated by {}'.format(job.pk, job, job.recipe.repository, signed_in_user))
  invalidate_job(request, job, message, same_client, client)
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

  recipes = models.Recipe.objects.filter(build_user=user, current=True).order_by('repository__name', 'cause', 'branch__name', 'name')\
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
      mev = ManualEvent.ManualEvent(user, branch, latest)
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
    message = "Activated by %s" % user
    models.JobChangeLog.objects.create(job=job, message=message)
    messages.info(request, 'Job activated')
  else:
    raise PermissionDenied('Activate job: {} is NOT a collaborator on {}'.format(user, job.recipe.repository))

  return redirect('ci:view_job', job_id=job.pk)

def post_event_change_to_pr(ev, action, comment, signed_in_user):
  """
  Makes a PR comment to notify of a change in event status.
  Input:
    event: models.Job: Job that has changed
    action: str: Describing what happend (like "canceled" or "invalidated")
    comment: str: Comment that was entered in by the user
    signed_in_user: models.GitUser: the initiating user
  """
  if ev.pull_request and ev.comments_url:
    auth = ev.build_user.start_session()
    gapi = ev.base.server().api()
    additional = ""
    if comment:
      additional = "\n\n%s" % comment
    pr_message = "All jobs on %s : %s by @%s%s" % (ev.head.sha[:7], action, signed_in_user, additional)
    gapi.pr_comment(auth, ev.comments_url, pr_message)

def cancel_event(request, event_id):
  """
  Cancel all jobs attached to an event
  """
  if request.method != 'POST':
    return HttpResponseNotAllowed(['POST'])

  ev = get_object_or_404(models.Event, pk=event_id)
  allowed, signed_in_user = Permissions.is_allowed_to_cancel(request.session, ev)

  if not allowed:
    messages.error(request, 'You are not allowed to cancel this event')
    return redirect('ci:view_event', event_id=ev.pk)

  comment = escape(request.POST.get("comment"))
  post_to_pr = request.POST.get("post_to_pr") == "on"
  event_url = reverse("ci:view_event", args=[ev.pk])
  message = "Parent <a href='%s'>event</a> canceled by %s" % (event_url, signed_in_user)
  if comment:
    message += " with comment: %s" % comment
  if post_to_pr:
    post_event_change_to_pr(ev, "canceled", comment, signed_in_user)

  event.cancel_event(ev, message)
  logger.info('Event {}: {} canceled by {}'.format(ev.pk, ev, signed_in_user))
  messages.info(request, 'Event {} canceled'.format(ev))

  return redirect('ci:view_event', event_id=ev.pk)

def set_job_canceled(job, msg=None):
  job.status = models.JobStatus.CANCELED
  job.complete = True
  job.save()
  job.event.status = models.JobStatus.CANCELED
  job.event.save()
  if msg:
    models.JobChangeLog.objects.create(job=job, message=msg)

def cancel_job(request, job_id):
  if request.method != 'POST':
    return HttpResponseNotAllowed(['POST'])

  job = get_object_or_404(models.Job, pk=job_id)
  allowed, signed_in_user = Permissions.is_allowed_to_cancel(request.session, job.event)
  if not allowed:
    return HttpResponseForbidden('Not allowed to cancel this job')

  message = "Canceled by %s" % signed_in_user
  comment = escape(request.POST.get('comment'))

  post_to_pr = request.POST.get('post_to_pr') == 'on'
  if post_to_pr:
    post_job_change_to_pr(job, "canceled", comment, signed_in_user)

  if comment:
    message += "\nwith comment: %s" % comment
  set_job_canceled(job, message)
  logger.info('Job {}: {} on {} canceled by {}'.format(job.pk, job, job.recipe.repository, signed_in_user))
  messages.info(request, 'Job {} canceled'.format(job))
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
  event_list = EventsStatus.get_default_events_query().filter(cause=models.Event.MANUAL)
  events = get_paginated(request, event_list)
  evs_info = EventsStatus.events_info(events)
  return render(request, 'ci/scheduled.html', {'events': evs_info, 'pages': events})

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
