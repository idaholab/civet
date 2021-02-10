
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

from __future__ import unicode_literals, absolute_import
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.http import HttpResponse, HttpResponseNotAllowed, HttpResponseForbidden, Http404
from django.urls import reverse
from django.core.exceptions import PermissionDenied
from django.conf import settings
from ci import models, event, forms
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.contrib import messages
from django.db.models import Prefetch
from datetime import timedelta
import time
import tarfile
from io import BytesIO
from ci import RepositoryStatus, EventsStatus, Permissions, PullRequestEvent, ManualEvent, TimeUtils
from django.utils.html import escape
from django.utils.text import get_valid_filename
from django.views.decorators.cache import never_cache
from ci.client import UpdateRemoteStatus
import os, re

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
            try:
                gitserver = models.GitServer.objects.get(host_type=server["type"], name=server["hostname"])
            except models.GitServer.DoesNotExist:
                # Probably shouldn't happen in production but it does seem to
                # happen during selenium testing
                continue
            user = gitserver.signed_in_user(request.session)
            if user != None:
                for repo in user.preferred_repos.filter(user__server=gitserver).all():
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

def sorted_clients(client_q):
    clients = [ c for c in client_q.all() ]
    clients.sort(key=lambda s: [int(t) if t.isdigit() else t.lower() for t in re.split(r'(\d+)', s.name)])
    return clients

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
        gitserver = models.GitServer.objects.get(host_type=server["type"], name=server["hostname"])
        user = gitserver.signed_in_user(request.session)
        if user != None:
            users[gitserver.pk] = user
            for repo in user.preferred_repos.filter(user__server=gitserver).all():
                current_repos.append(repo.pk)
        q = models.Repository.objects.filter(active=True, user__server=gitserver).order_by('user__name', 'name').all()
        for repo in q:
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
    allowed = Permissions.is_collaborator(request.session, ev.build_user, ev.base.repo())
    current_alt = []
    alt_choices = []
    default_choices = []
    if allowed:
        alt_recipes = (models.Recipe.objects
                .filter(repository=pr.repository,
                    build_user=ev.build_user,
                    current=True,
                    active=True,
                    cause=models.Recipe.CAUSE_PULL_REQUEST_ALT,)
                .order_by("display_name"))

        default_recipes = (models.Recipe.objects
                .filter(repository=pr.repository,
                    build_user=ev.build_user,
                    current=True,
                    active=True,
                    cause=models.Recipe.CAUSE_PULL_REQUEST,)
                .order_by("display_name"))

        push_recipes = (models.Recipe.objects
                .filter(repository=pr.repository,
                    build_user=ev.build_user,
                    current=True,
                    active=True,
                    cause=models.Recipe.CAUSE_PUSH,)
                .order_by("display_name"))

        default_recipes = [r for r in default_recipes.all()]
        current_alt = [ r.pk for r in pr.alternate_recipes.all() ]
        current_default = [j.recipe.filename for j in pr.events.latest("created").jobs.all() ]
        push_map = {r.filename: r.branch for r in push_recipes.all()}
        alt_choices = []
        for r in alt_recipes:
            alt_choices.append({"recipe": r,
                "selected": r.pk in current_alt,
                "push_branch": push_map.get(r.filename),
                })

        default_choices = []
        for r in default_recipes:
            default_choices.append({"recipe": r,
                "pk": r.pk,
                "disabled": r.filename in current_default,
                "push_branch": push_map.get(r.filename),
                })

        if alt_choices and request.method == "POST":
            form_choices = [ (r.pk, r.display_name) for r in alt_recipes ]
            form = forms.AlternateRecipesForm(request.POST)
            form.fields["recipes"].choices = form_choices
            form_default_choices = []
            for r in default_choices:
                if not r["disabled"]:
                    form_default_choices.append((r["pk"], r["recipe"].display_name))
            form.fields["default_recipes"].choices = form_default_choices
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
                selected_default_recipes = []
                if form.cleaned_data["default_recipes"]:
                    q = models.Recipe.objects.filter(pk__in=form.cleaned_data["default_recipes"])
                    selected_default_recipes = [r for r in q]
                pr_event.create_pr_alternates(pr, default_recipes=selected_default_recipes)
                # update the choices so the new form is correct
                current_alt = [ r.pk for r in pr.alternate_recipes.all() ]
                alt_choices = [ {"recipe": r, "selected": r.pk in current_alt} for r in alt_recipes ]
            else:
                messages.warning(request, "Invalid form")
                logger.warning("Invalid form")
                for field, errors in form.errors.items():
                    logger.warning("Form error in field: %s: %s" % (field, errors))

    events = EventsStatus.events_with_head(pr.events)
    evs_info = EventsStatus.multiline_events_info(events, events_url=True)
    context = { "pr": pr,
        "events": evs_info,
        "allowed": allowed,
        "update_interval": settings.EVENT_PAGE_UPDATE_INTERVAL,
        "alt_choices": alt_choices,
        "default_choices": default_choices,
        }
    return render(request, 'ci/pr.html', context)

def view_event(request, event_id):
    """
    Show the details of an Event
    """
    ev = get_object_or_404(EventsStatus.events_with_head(), pk=event_id)
    evs_info = EventsStatus.multiline_events_info([ev])
    allowed = Permissions.is_collaborator(request.session, ev.build_user, ev.base.repo())
    has_unactivated = ev.jobs.filter(active=False).count() != 0
    context = {'event': ev,
        'events': evs_info,
        'allowed_to_cancel': allowed,
        "update_interval": settings.EVENT_PAGE_UPDATE_INTERVAL,
        "has_unactivated": has_unactivated,
        }
    return render(request, 'ci/event.html', context)

def get_job_results(request, job_id):
    """
    Just download all the output of the job into a tarball.
    """
    job = get_object_or_404(models.Job.objects.select_related('recipe',).prefetch_related('step_results'), pk=job_id)
    perms = Permissions.job_permissions(request.session, job)
    if not perms['can_see_results']:
        return HttpResponseForbidden('Not allowed to see results')

    response = HttpResponse(content_type='application/x-gzip')
    base_name = 'results_{}_{}'.format(job.pk, get_valid_filename(job.recipe.name))
    response['Content-Disposition'] = 'attachment; filename="{}.tar.gz"'.format(base_name)
    tar = tarfile.open(fileobj=response, mode='w:gz')
    for result in job.step_results.all():
        info = tarfile.TarInfo(name='{}/{:02}_{}'.format(base_name, result.position, get_valid_filename(result.name)))
        s = BytesIO(result.plain_output().replace('\u2018', "'").replace("\u2019", "'").encode("utf-8", "replace"))
        buf = s.getvalue()
        info.size = len(buf)
        info.mtime = time.time()
        tar.addfile(tarinfo=info, fileobj=s)
    tar.close()
    return response

def view_job(request, job_id):
    """
    View the details of a job, along
    with any results.
    """
    recipe_q = models.Recipe.objects.prefetch_related("depends_on", "auto_authorized", "viewable_by_teams")
    q = (models.Job.objects
            .select_related('recipe__repository__user__server',
                'recipe__build_user__server',
                'event__pull_request',
                'event__base__branch__repository__user__server',
                'event__head__branch__repository__user__server',
                'config',
                'client',)
            .prefetch_related(Prefetch("recipe", queryset=recipe_q),
                'step_results',
                'changelog'))
    job = get_object_or_404(q, pk=job_id)
    perms = Permissions.job_permissions(request.session, job)
    clients = None
    if perms['can_see_client']:
        clients = sorted_clients(models.Client.objects.exclude(status=models.Client.DOWN))
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

def do_repo_page(request, repo):
    """
    Render the repo page. This has the same layout as the main page but only for single repository.
    Input:
        request[django.http.HttpRequest]
        repo[models.Repository]
    """
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

def view_owner_repo(request, owner, repo):
    """
    Render the repo page given the owner and repo
    Input:
        request[django.http.HttpRequest]
        owner[str]: The owner of the repository
        repo[str]: The name of the repository
    """
    repo = get_object_or_404(models.Repository.objects.select_related('user__server'), name=repo, user__name=owner)
    return do_repo_page(request, repo)

def view_repo(request, repo_id):
    """
    Render the repo page given the internal DB id of the repo
    Input:
        request[django.http.HttpRequest]
        repo_id[int]: The internal DB id of the repo
    """
    repo = get_object_or_404(models.Repository.objects.select_related('user__server'), pk=repo_id)
    return do_repo_page(request, repo)

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

def do_branch_page(request, branch):
    """
    Render the branch page given a branch object
    Input:
        request[django.http.HttpRequest]
        branch[models.Branch]
    """
    if request.method != "GET":
        return HttpResponseNotAllowed(['GET'])

    causes = []
    if request.GET.get("do_filter", "0") == "0":
        causes = [models.Event.PUSH, models.Event.MANUAL, models.Event.RELEASE]
        form = forms.BranchEventsForm(initial={"filter_events": causes})
    else:
        form = forms.BranchEventsForm(request.GET)
        if form.is_valid():
            causes = [int(c) for c in form.cleaned_data["filter_events"]]

    event_list = EventsStatus.get_default_events_query().filter(base__branch=branch, cause__in=causes)
    events = get_paginated(request, event_list)
    evs_info = EventsStatus.multiline_events_info(events)
    return render(request, 'ci/branch.html', {"form": form, 'branch': branch, 'events': evs_info, 'pages': events})

def view_repo_branch(request, owner, repo, branch):
    """
    Render the branch page based on owner/repo/branch
    Input:
        request[django.http.HttpRequest]
        owner[str]: Owner of the repository
        repo[str]: Name of the repository
        branch[str]: Name of the branch
    """
    q = models.Branch.objects.select_related("repository__user__server")
    branch = get_object_or_404(q, name=branch, repository__name=repo, repository__user__name=owner)
    return do_branch_page(request, branch)

def view_branch(request, branch_id):
    """
    Render the branch page based on a branch id
    Input:
        request[django.http.HttpRequest]
        branch_id[int]: Internal DB id of the branch
    """
    branch = get_object_or_404(models.Branch.objects.select_related("repository__user__server"), pk=int(branch_id))
    return do_branch_page(request, branch)

def view_user(request, username):
    """
    Render the user page based on username
    Input:
        request[django.http.HttpRequest]
        username[str]: Name of the user
    """
    users = models.GitUser.objects.filter(name=username)
    if users.count() == 0:
        raise Http404('Bad username')

    repos = RepositoryStatus.get_user_repos_with_open_prs_status(username)
    pr_ids = []
    for r in repos:
        for pr in r["prs"]:
            pr_ids.append(pr["id"])
    event_list = EventsStatus.get_single_event_for_open_prs(pr_ids)
    evs_info = EventsStatus.multiline_events_info(event_list)
    data = {'username': username, 'repos': repos, 'events': evs_info, "update_interval": settings.EVENT_PAGE_UPDATE_INTERVAL,}
    return render(request, 'ci/user.html', data)

def pr_list(request):
    pr_list = (models.PullRequest.objects
                .order_by('-created')
                .select_related('repository__user__server')
                .order_by('repository__user__name', 'repository__name', 'number'))
    prs = get_paginated(request, pr_list)
    return render(request, 'ci/prs.html', {'prs': prs})

def branch_list(request):
    branch_list = (models.Branch.objects
                    .exclude(status=models.JobStatus.NOT_STARTED)
                    .select_related('repository__user__server')
                    .order_by('repository__user__name', 'repository__name', 'name'))
    branches = get_paginated(request, branch_list)
    return render(request, 'ci/branches.html', {'branches': branches})

def client_list(request):
    allowed = Permissions.is_allowed_to_see_clients(request.session)
    if not allowed:
        return render(request, 'ci/clients.html', {'clients': None, 'allowed': False})

    client_list = clients_info()
    data = {'clients': client_list, 'allowed': True, 'update_interval': settings.HOME_PAGE_UPDATE_INTERVAL, }
    return render(request, 'ci/clients.html', data)

def clients_info():
    """
    Gets the information on all the currently active clients.
    Retruns:
      list of dicts containing client information
    """
    sclients = sorted_clients(models.Client.objects.exclude(status=models.Client.DOWN))
    active_clients = [] # clients that we've seen in <= 60 s
    inactive_clients = [] # clients that we've seen in > 60 s
    for c in sclients:
        d = {'pk': c.pk,
            "ip": c.ip,
            "name": c.name,
            "message": c.status_message,
            "status": c.status_str(),
            "lastseen": TimeUtils.human_time_str(c.last_seen),
            }
        if c.unseen_seconds() > 2*7*24*60*60: # 2 weeks
            # do it like this so that last_seen doesn't get updated
            models.Client.objects.filter(pk=c.pk).update(status=models.Client.DOWN)
        elif c.unseen_seconds() > 60:
            d["status_class"] = "client_NotSeen"
            inactive_clients.append(d)
        else:
            d["status_class"] = "client_%s" % c.status_slug()
            active_clients.append(d)
    clients = [] # sort these so that active clients (seen in < 60 s) are first
    for d in active_clients:
        clients.append(d)
    for d in inactive_clients:
        clients.append(d)
    return clients

def event_list(request):
    event_list = EventsStatus.get_default_events_query()
    events = get_paginated(request, event_list)
    evs_info = EventsStatus.multiline_events_info(events)
    return render(request, 'ci/events.html', {'events': evs_info, 'pages': events})

def sha_events(request, owner, repo, sha):
    repo = get_object_or_404(models.Repository.objects, name=repo, user__name=owner)
    event_q = models.Event.objects.filter(head__branch__repository=repo, head__sha__startswith=sha)
    event_list = EventsStatus.get_default_events_query(event_q)
    events = get_paginated(request, event_list)
    evs_info = EventsStatus.multiline_events_info(events)
    return render(request, 'ci/events.html',
            {'events': evs_info, 'pages': events, 'sha': sha, 'repo': repo})

def recipe_events(request, recipe_id):
    recipe = get_object_or_404(models.Recipe, pk=recipe_id)
    event_list = (EventsStatus
                    .get_default_events_query()
                    .filter(jobs__recipe__filename=recipe.filename, jobs__recipe__cause=recipe.cause))
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
    evs_info = EventsStatus.multiline_events_info(events)
    avg = timedelta(seconds=total)
    data = {'recipe': recipe,
            'events': evs_info,
            'average_time': avg,
            'pages': events,
            }
    return render(request, 'ci/recipe_events.html', data)

def invalidate_job(request, job, message, same_client=False, client=None, check_ready=True):
    """
    Convience function to invalidate a job and show a message to the user.
    Input:
      request: django.http.HttpRequest
      job. models.Job
      same_client: bool
    """
    job.set_invalidated(message, same_client, client, check_ready)
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
    allowed = Permissions.is_collaborator(request.session, ev.build_user, ev.base.repo())
    if not allowed:
        messages.error(request, 'You need to be signed in and be a collaborator to invalidate results.')
        return redirect('ci:view_event', event_id=ev.pk)

    signed_in_user = ev.base.server().signed_in_user(request.session)
    comment = escape(request.POST.get("comment"))
    logger.info('Event {}: {} invalidated by {}'.format(ev.pk, ev, signed_in_user))
    event_url = reverse("ci:view_event", args=[ev.pk])
    message = "Parent <a href='%s'>event</a> invalidated by %s" % (event_url, signed_in_user)
    if comment:
        message += " with comment: %s" % comment

    post_to_pr = request.POST.get("post_to_pr") == "on"
    if post_to_pr:
        post_event_change_to_pr(request, ev, "invalidated", comment, signed_in_user)

    same_client = request.POST.get('same_client') == "on"
    for job in ev.jobs.all():
        invalidate_job(request, job, message, same_client, check_ready=False)
    # Only do this once so that we get the job dependencies setup correctly.
    ev.make_jobs_ready()

    return redirect('ci:view_event', event_id=ev.pk)

def post_job_change_to_pr(request, job, action, comment, signed_in_user):
    """
    Makes a PR comment to notify of a change in job status.
    Input:
      job: models.Job: Job that has changed
      action: str: Describing what happend (like "canceled" or "invalidated")
      comment: str: Comment that was entered in by the user
      signed_in_user: models.GitUser: the initiating user
    """
    if job.event.pull_request and job.event.comments_url:
        gapi = job.event.build_user.api()
        additional = ""
        if comment:
            additional = "\n\n%s" % comment
        abs_job_url = request.build_absolute_uri(reverse('ci:view_job', args=[job.pk]))
        pr_message = "Job [%s](%s) on %s : %s by @%s%s" % (job.unique_name(),
                abs_job_url,
                job.event.head.short_sha(),
                action,
                signed_in_user,
                additional)
        gapi.pr_comment(job.event.comments_url, pr_message)

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
    allowed = Permissions.is_collaborator(request.session, job.event.build_user, job.event.base.repo())
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
    signed_in_user = job.event.base.server().signed_in_user(request.session)
    message = "Invalidated by %s" % signed_in_user
    if comment:
        message += "\nwith comment: %s" % comment

    if post_to_pr:
        post_job_change_to_pr(request, job, "invalidated", comment, signed_in_user)

    logger.info('Job {}: {} on {} invalidated by {}'.format(job.pk, job, job.recipe.repository, signed_in_user))
    invalidate_job(request, job, message, same_client, client)
    return redirect('ci:view_job', job_id=job.pk)

def sort_recipes_key(entry):
    return str(entry[0].repository)

def view_profile(request, server_type, server_name):
    """
    View the recipes that the user owns
    """
    server = get_object_or_404(models.GitServer, host_type=server_type, name=server_name)
    user = server.signed_in_user(request.session)
    if not user:
        request.session['source_url'] = request.build_absolute_uri()
        return redirect(server.api().sign_in_url())

    recipes = (models.Recipe.objects
                    .filter(build_user=user, current=True)
                    .order_by('repository__name', 'cause', 'branch__name', 'name')
                    .select_related('branch', 'repository__user')\
                    .prefetch_related('build_configs', 'depends_on'))
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
def manual_branch(request, build_key, branch_id, label=""):
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
        latest = user.api().last_sha(branch.repository.user.name, branch.repository.name, branch.name)
        force = bool(int(request.POST.get('force', 0)))
        update_branch_status = bool(int(request.POST.get('update_branch_status', 1)))
        if latest:
            mev = ManualEvent.ManualEvent(user, branch, latest, label)
            mev.force = force
            mev.save(update_branch_status)
            reply = 'Success. Scheduled recipes on branch %s for user %s' % (branch, user)
            messages.info(request, reply)
            logger.info(reply)
        else:
            reply = "Failed to get latest SHA for %s" % branch
    except Exception:
        reply = 'Error running manual for user %s on branch %s\nError: %s'\
            % (user, branch, traceback.format_exc())
        messages.error(request, reply)

    logger.info(reply)
    next_url = request.POST.get('next', None)
    if next_url:
        return redirect(next_url)
    return HttpResponse(reply)

def set_job_active(request, job, user):
    """
    Sets an inactive job to active and check to see if it is ready to run
    Returns a bool indicating if it changed the job.
    """
    if job.active:
        return False

    job.active = True
    job.event.complete = False
    job.set_status(models.JobStatus.NOT_STARTED, calc_event=True) # will save job and event
    message = "Activated by %s" % user
    models.JobChangeLog.objects.create(job=job, message=message)
    messages.info(request, 'Job %s activated' % job)
    return True

def activate_event(request, event_id):
    """
    Endpoint for activating all jobs on an event
    """
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])

    ev = get_object_or_404(models.Event, pk=event_id)
    jobs = ev.jobs.filter(active=False).order_by('-created')
    if jobs.count() == 0:
        messages.info(request, 'No jobs to activate')
        return redirect('ci:view_event', event_id=ev.pk)

    repo = jobs.first().recipe.repository
    user = repo.server().signed_in_user(request.session)
    if not user:
        raise PermissionDenied('You need to be signed in to activate jobs')

    collab = Permissions.is_collaborator(request.session, ev.build_user, repo, user=user)
    if collab:
        activated_jobs = []
        for j in jobs.all():
            if set_job_active(request, j, user):
                activated_jobs.append(j)
        for j in activated_jobs:
            j.init_pr_status()
        ev.make_jobs_ready()
    else:
        raise PermissionDenied('Activate event: {} is NOT a collaborator on {}'.format(user, repo))

    return redirect('ci:view_event', event_id=ev.pk)

def activate_job(request, job_id):
    """
    Endpoint for activating a job
    """
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])

    job = get_object_or_404(models.Job, pk=job_id)
    server = job.recipe.repository.server()
    user = server.signed_in_user(request.session)
    if not user:
        raise PermissionDenied('You need to be signed in to activate a job')

    collab = Permissions.is_collaborator(request.session, job.event.build_user, job.recipe.repository, user=user)
    if collab:
        if set_job_active(request, job, user):
            job.init_pr_status()
        job.event.make_jobs_ready()
    else:
        raise PermissionDenied('Activate job: {} is NOT a collaborator on {}'.format(user, job.recipe.repository))

    return redirect('ci:view_job', job_id=job.pk)

def post_event_change_to_pr(request, ev, action, comment, signed_in_user):
    """
    Makes a PR comment to notify of a change in event status.
    Input:
      event: models.Job: Job that has changed
      action: str: Describing what happend (like "canceled" or "invalidated")
      comment: str: Comment that was entered in by the user
      signed_in_user: models.GitUser: the initiating user
    """
    if ev.pull_request and ev.comments_url:
        gapi = ev.build_user.api()
        additional = ""
        if comment:
            additional = "\n\n%s" % comment
        abs_ev_url = request.build_absolute_uri(reverse('ci:view_event', args=[ev.pk]))
        pr_message = "All [jobs](%s) on %s : %s by @%s%s" % (abs_ev_url,
                ev.head.short_sha(),
                action,
                signed_in_user,
                additional)
        gapi.pr_comment(ev.comments_url, pr_message)

def cancel_event(request, event_id):
    """
    Cancel all jobs attached to an event
    """
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])

    ev = get_object_or_404(models.Event, pk=event_id)
    allowed = Permissions.is_collaborator(request.session, ev.build_user, ev.base.repo())

    if not allowed:
        messages.error(request, 'You are not allowed to cancel this event')
        return redirect('ci:view_event', event_id=ev.pk)

    signed_in_user = ev.base.server().signed_in_user(request.session)
    comment = escape(request.POST.get("comment"))
    post_to_pr = request.POST.get("post_to_pr") == "on"
    event_url = reverse("ci:view_event", args=[ev.pk])
    message = "Parent <a href='%s'>event</a> canceled by %s" % (event_url, signed_in_user)
    if comment:
        message += " with comment: %s" % comment
    if post_to_pr:
        post_event_change_to_pr(request, ev, "canceled", comment, signed_in_user)

    event.cancel_event(ev, message, True)
    logger.info('Event {}: {} canceled by {}'.format(ev.pk, ev, signed_in_user))
    messages.info(request, 'Event {} canceled'.format(ev))

    return redirect('ci:view_event', event_id=ev.pk)

def set_job_canceled(job, msg=None, status=models.JobStatus.CANCELED):
    job.complete = True
    job.set_status(status, calc_event=True) # This will save the job
    if msg:
        models.JobChangeLog.objects.create(job=job, message=msg)

def cancel_job(request, job_id):
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])

    job = get_object_or_404(models.Job, pk=job_id)
    allowed = Permissions.is_collaborator(request.session, job.event.build_user, job.event.base.repo())
    if not allowed:
        return HttpResponseForbidden('Not allowed to cancel this job')

    signed_in_user = job.event.base.server().signed_in_user(request.session)
    message = "Canceled by %s" % signed_in_user
    comment = escape(request.POST.get('comment'))

    post_to_pr = request.POST.get('post_to_pr') == 'on'
    if post_to_pr:
        post_job_change_to_pr(request, job, "canceled", comment, signed_in_user)

    if comment:
        message += "\nwith comment: %s" % comment
    set_job_canceled(job, message)
    UpdateRemoteStatus.job_complete(job)
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
    evs_info = EventsStatus.multiline_events_info(events)
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

def get_branch_status(branch):
    """
    Returns an SVG image of the status of a branch.
    Input:
        branch[models.Branch]: Branch to get the image for
    """
    if branch.status == models.JobStatus.NOT_STARTED:
        raise Http404('Branch not active')

    m = { models.JobStatus.SUCCESS: "CIVET-passed-green.svg",
        models.JobStatus.FAILED: "CIVET-failed-red.svg",
        models.JobStatus.FAILED_OK: "CIVET-failed_but_allowed-orange.svg",
        models.JobStatus.RUNNING: "CIVET-running-yellow.svg",
        models.JobStatus.CANCELED: "CIVET-canceled-lightgrey.svg",
        }
    static_file = m[branch.status]
    this_dir = os.path.dirname(__file__)
    full_path = os.path.join(this_dir, "static", "third_party", "shields.io", static_file)
    with open(full_path, "r") as f:
        data = f.read()
        return HttpResponse(data, content_type="image/svg+xml")

@never_cache
def repo_branch_status(request, owner, repo, branch):
    """
    Returns an SVG image of the status of a branch.
    This is intended to be used for build status "badges"
    Input:
      owner[str]: Owner of the repository
      repo[str]: Name of the repository
      branch[str]: Name of the branch
    """
    if request.method != "GET":
        return HttpResponseNotAllowed(['GET'])

    branch_obj = get_object_or_404(models.Branch.objects, repository__user__name=owner, repository__name=repo, name=branch)
    return get_branch_status(branch_obj)

@never_cache
def branch_status(request, branch_id):
    """
    Returns an SVG image of the status of a branch.
    This is intended to be used for build status "badges"
    Input:
      branch_id[int]: Id Of the branch to get the status
    """
    if request.method != "GET":
        return HttpResponseNotAllowed(['GET'])

    branch = get_object_or_404(models.Branch.objects, pk=int(branch_id))
    return get_branch_status(branch)
