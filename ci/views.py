# Copyright 2016-2025 Battelle Energy Alliance, LLC
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
from django.http import (
    HttpResponse,
    HttpResponseNotAllowed,
    HttpResponseForbidden,
    Http404,
)
from django.urls import reverse
from django.core.exceptions import PermissionDenied
from django.conf import settings
from ci import models, event, forms, tasks
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.contrib import messages
from django.db.models import Prefetch, Max
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from datetime import timedelta
import time
import tarfile
from io import BytesIO
from ci import (
    RepositoryStatus,
    EventsStatus,
    Permissions,
    PullRequestEvent,
    ManualEvent,
    TimeUtils,
)
from ci.client.ReadyJobs import get_ready_jobs
from django.utils.html import escape
from django.utils.text import get_valid_filename
from django.views.decorators.cache import never_cache
from ci.client import UpdateRemoteStatus
import os, re
from datetime import datetime
from croniter import croniter
import pytz
from collections import defaultdict

import logging

logger = logging.getLogger("ci")


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
    viewable_repos = Permissions.viewable_repos(request.session)
    pks = []
    default = request.GET.get("default")
    if default is None:
        default = False
        for server in settings.INSTALLED_GITSERVERS:
            try:
                gitserver = models.GitServer.objects.get(
                    host_type=server["type"], name=server["hostname"]
                )
            except models.GitServer.DoesNotExist:
                # Probably shouldn't happen in production but it does seem to
                # happen during selenium testing
                continue
            user = gitserver.signed_in_user(request.session)
            if user != None:
                repos = user.preferred_repos.filter(
                    user__server=gitserver, id__in=viewable_repos
                )
                for repo in repos.all():
                    pks.append(repo.pk)
    else:
        default = True
    if pks:
        repos = RepositoryStatus.filter_repos_status(pks, last_modified=last_modified)
        evs_info = EventsStatus.events_filter_by_repo(
            pks, limit=limit, last_modified=last_modified
        )
    else:
        repos = RepositoryStatus.main_repos_status(
            last_modified=last_modified, filter_repo_ids=viewable_repos
        )
        evs_info = EventsStatus.all_events_info(
            limit=limit, last_modified=last_modified, filter_repo_ids=viewable_repos
        )

    return repos, evs_info, default


def sorted_clients(client_q):
    clients = [c for c in client_q.all()]
    clients.sort(
        key=lambda s: [
            int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", s.name)
        ]
    )
    return clients


def render_unauthorized_repo(request, repo):
    """
    Helper for rendering an unauthorized repo, if any.
    This renders the same page as a missing object so that the existence
    of a repository that the user can't see isn't revealed.
    Input:
      request: django.http.HttpRequest
      repo: Repository
    Return:
      A rendered 404 page if unauthorized, otherwise none
    """
    if not Permissions.can_view_repo(request.session, repo):
        server = repo.user.server
        user = server.signed_in_user(request.session)
        uri = request.build_absolute_uri()
        logger.info(
            f"User {user} does not have permission to view {uri} for {server}/{repo}"
        )
        return page_not_found(request, None)
    return None


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
    return render(
        request,
        "ci/main.html",
        {
            "repos": repos,
            "recent_events": evs_info,
            "last_request": TimeUtils.get_local_timestamp(),
            "event_limit": limit,
            "update_interval": settings.HOME_PAGE_UPDATE_INTERVAL,
            "default_view": default,
        },
    )


def user_repo_settings(request):
    """
    Allow the user to change the default view on the main page.
    Input:
      request: django.http.HttpRequest
    Return:
      django.http.HttpResponse based object
    """
    viewable_repos = Permissions.viewable_repos(request.session)
    current_repos = []
    all_repos = []
    users = {}
    for server in settings.INSTALLED_GITSERVERS:
        gitserver = models.GitServer.objects.get(
            host_type=server["type"], name=server["hostname"]
        )
        user = gitserver.signed_in_user(request.session)
        if user != None:
            users[gitserver.pk] = user
            repos_q = user.preferred_repos.filter(
                user__server=gitserver, id__in=viewable_repos
            )
            for repo in repos_q.all():
                current_repos.append(repo.pk)
        repos_q = models.Repository.objects.filter(
            active=True, user__server=gitserver, id__in=viewable_repos
        )
        repos_q = repos_q.order_by("user__name", "name").all()
        for repo in repos_q.all():
            all_repos.append((repo.pk, str(repo)))

    if not users:
        messages.error(request, "You need to be signed in to set preferences")
        return render(request, "ci/repo_settings.html", {"form": None})

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

    return render(request, "ci/repo_settings.html", {"form": form})


# Pages for the objects that the purge_old_prs command deletes. Maps the view
# name to the model, the URL keyword argument holding the pk, and a display name.
PURGEABLE_PAGES = {
    "ci:view_event": (models.Event, "event_id", "event"),
    "ci:view_pr": (models.PullRequest, "pr_id", "pull request"),
    "ci:view_job": (models.Job, "job_id", "job"),
    "ci:job_results": (models.Job, "job_id", "job"),
}


def page_not_found(request, exception):
    """
    Renders the 404 page. For pages of objects that purge_old_prs deletes, says
    whether the object most likely existed and was deleted. Nothing is stored
    about deleted objects, but pks are assigned in increasing order, so a
    missing pk below the largest existing one most likely belonged to an
    object that was deleted.
    """
    context = {}
    match = request.resolver_match
    if match is not None and match.view_name in PURGEABLE_PAGES:
        model, kwarg, name = PURGEABLE_PAGES[match.view_name]
        max_pk = model.objects.aggregate(Max("pk"))["pk__max"]
        context["object_name"] = name
        context["deleted"] = max_pk is not None and int(match.kwargs[kwarg]) < max_pk
    return render(request, "ci/404.html", context, status=404)


def view_pr(request, pr_id):
    """
    Show the details of a PR
    Input:
      request: django.http.HttpRequest
      pr_id: pk of models.PullRequest
    Return:
      django.http.HttpResponse based object
    """
    pr = get_object_or_404(
        models.PullRequest.objects.select_related("repository__user"), pk=pr_id
    )

    unauthorized = render_unauthorized_repo(request, pr.repository)
    if unauthorized is not None:
        return unauthorized

    # A closed pull request has no events while purge_old_prs is deleting it
    try:
        ev = pr.events.select_related(
            "build_user", "base__branch__repository__user__server"
        ).latest()
    except models.Event.DoesNotExist:
        raise Http404("Pull request has no events")
    # Only users with write access can see and add non-default recipes
    allowed = Permissions.has_write_access(
        request.session, ev.build_user, ev.base.repo()
    )
    current_alt = []
    alt_choices = []
    default_choices = []
    if allowed:
        alt_recipes = models.Recipe.objects.filter(
            repository=pr.repository,
            build_user=ev.build_user,
            current=True,
            active=True,
            cause=models.Recipe.CAUSE_PULL_REQUEST_ALT,
        ).order_by("display_name")

        default_recipes = models.Recipe.objects.filter(
            repository=pr.repository,
            build_user=ev.build_user,
            current=True,
            active=True,
            cause=models.Recipe.CAUSE_PULL_REQUEST,
        ).order_by("display_name")

        push_recipes = models.Recipe.objects.filter(
            repository=pr.repository,
            build_user=ev.build_user,
            current=True,
            active=True,
            cause=models.Recipe.CAUSE_PUSH,
        ).order_by("display_name")

        default_recipes = [r for r in default_recipes.all()]
        current_alt = [r.pk for r in pr.alternate_recipes.all()]
        current_default = [
            j.recipe.filename for j in pr.events.latest("created").jobs.all()
        ]
        push_map = {r.filename: r.branch for r in push_recipes.all()}
        alt_choices = []
        for r in alt_recipes:
            alt_choices.append(
                {
                    "recipe": r,
                    "selected": r.pk in current_alt,
                    "push_branch": push_map.get(r.filename),
                }
            )

        default_choices = []
        for r in default_recipes:
            default_choices.append(
                {
                    "recipe": r,
                    "pk": r.pk,
                    "disabled": r.filename in current_default,
                    "push_branch": push_map.get(r.filename),
                }
            )

        if alt_choices and request.method == "POST":
            form_choices = [(r.pk, r.display_name) for r in alt_recipes]
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
                pr.events.latest("created").save()
                messages.info(request, "Success")
                pr_event = PullRequestEvent.PullRequestEvent()
                selected_default_recipes = []
                if form.cleaned_data["default_recipes"]:
                    q = models.Recipe.objects.filter(
                        pk__in=form.cleaned_data["default_recipes"]
                    )
                    selected_default_recipes = [r for r in q]
                pr_event.create_pr_alternates(
                    pr, default_recipes=selected_default_recipes
                )
                # update the choices so the new form is correct
                current_alt = [r.pk for r in pr.alternate_recipes.all()]
                for choice in alt_choices:
                    choice["selected"] = choice["recipe"].pk in current_alt
            else:
                messages.warning(request, "Invalid form")
                logger.warning("Invalid form")
                for field, errors in form.errors.items():
                    logger.warning("Form error in field: %s: %s" % (field, errors))

    events = EventsStatus.events_with_head(pr.events)
    evs_info = EventsStatus.multiline_events_info(events, events_url=True)
    context = {
        "pr": pr,
        "events": evs_info,
        "allowed": allowed,
        "update_interval": settings.EVENT_PAGE_UPDATE_INTERVAL,
        "alt_choices": alt_choices,
        "default_choices": default_choices,
    }
    return render(request, "ci/pr.html", context)


def view_event(request, event_id):
    """
    Show the details of an Event
    """
    q = EventsStatus.events_with_head().select_related("base__branch__repository")
    ev = get_object_or_404(q, pk=event_id)

    unauthorized = render_unauthorized_repo(request, ev.base.repo())
    if unauthorized is not None:
        return unauthorized

    evs_info = EventsStatus.multiline_events_info([ev])
    has_unactivated = ev.jobs.filter(active=False).count() != 0
    can_see_results = Permissions.can_see_event_results(request.session, ev)
    context = {
        "event": ev,
        "events": evs_info,
        "allowed_to_activate": Permissions.has_write_access(
            request.session, ev.build_user, ev.base.repo()
        ),
        "allowed_to_cancel": can_see_results
        and Permissions.can_cancel(request.session, ev),
        "allowed_to_invalidate": can_see_results
        and Permissions.can_invalidate(request.session, ev),
        "allowed_to_prioritize": Permissions.is_server_admin(
            request.session, ev.base.server()
        ),
        "update_interval": settings.EVENT_PAGE_UPDATE_INTERVAL,
        "has_unactivated": has_unactivated,
    }
    return render(request, "ci/event.html", context)


def get_job_results(request, job_id):
    """
    Just download all the output of the job into a tarball.
    """
    q = models.Job.objects.select_related("recipe__repository").prefetch_related(
        "step_results"
    )
    job = get_object_or_404(q, pk=job_id)

    unauthorized = render_unauthorized_repo(request, job.recipe.repository)
    if unauthorized is not None:
        return unauthorized

    perms = Permissions.job_permissions(request.session, job)
    if not perms["can_see_results"]:
        return HttpResponseForbidden("Not allowed to see results")

    response = HttpResponse(content_type="application/x-gzip")
    base_name = "results_{}_{}".format(job.pk, get_valid_filename(job.recipe.name))
    response["Content-Disposition"] = 'attachment; filename="{}.tar.gz"'.format(
        base_name
    )
    tar = tarfile.open(fileobj=response, mode="w:gz")
    for result in job.step_results.all():
        info = tarfile.TarInfo(
            name="{}/{:02}_{}".format(
                base_name, result.position, get_valid_filename(result.name)
            )
        )
        s = BytesIO(
            result.plain_output()
            .replace("\u2018", "'")
            .replace("\u2019", "'")
            .encode("utf-8", "replace")
        )
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
    recipe_q = models.Recipe.objects.prefetch_related(
        "depends_on", "auto_authorized", "viewable_by_teams"
    )
    q = models.Job.objects.select_related(
        "recipe__repository__user__server",
        "recipe__build_user__server",
        "event__pull_request",
        "event__base__branch__repository__user__server",
        "event__head__branch__repository__user__server",
        "config",
        "client",
    ).prefetch_related(
        Prefetch("recipe", queryset=recipe_q),
        "step_results",
        Prefetch(
            "changelog",
            queryset=models.JobChangeLog.objects.select_related("client", "event"),
        ),
    )
    job = get_object_or_404(q, pk=job_id)

    unauthorized = render_unauthorized_repo(request, job.event.base.repo())
    if unauthorized is not None:
        return unauthorized

    perms = Permissions.job_permissions(request.session, job)
    clients = None
    if perms["can_see_client"]:
        clients = sorted_clients(
            models.Client.objects.exclude(status=models.Client.DOWN).filter(
                disabled=False
            )
        )
    perms["job"] = job
    perms["clients"] = clients
    perms["update_interval"] = settings.JOB_PAGE_UPDATE_INTERVAL
    return render(request, "ci/job.html", perms)


def get_paginated(request, obj_list, obj_per_page=30):
    limit = request.GET.get("limit")
    if limit:
        obj_per_page = min(int(limit), 500)

    paginator = Paginator(obj_list, obj_per_page)

    page = request.GET.get("page")
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
    if copy_get.get("page"):
        del copy_get["page"]
    copy_get["limit"] = obj_per_page
    objs.get_params = copy_get.urlencode()
    return objs


def do_repo_page(request, repo):
    """
    Render the repo page. This has the same layout as the main page but only for single repository.
    Input:
        request[django.http.HttpRequest]
        repo[models.Repository]
    """
    unauthorized = render_unauthorized_repo(request, repo)
    if unauthorized is not None:
        return unauthorized

    limit = 30
    repos_status = RepositoryStatus.filter_repos_status([repo.pk])
    events_info = EventsStatus.events_filter_by_repo([repo.pk], limit=limit)

    params = {
        "repo": repo,
        "repos_status": repos_status,
        "events_info": events_info,
        "event_limit": limit,
        "last_request": TimeUtils.get_local_timestamp(),
        "update_interval": settings.HOME_PAGE_UPDATE_INTERVAL,
    }
    return render(request, "ci/repo.html", params)


def view_owner_repo(request, owner, repo):
    """
    Render the repo page given the owner and repo
    Input:
        request[django.http.HttpRequest]
        owner[str]: The owner of the repository
        repo[str]: The name of the repository
    """
    repo = get_object_or_404(
        models.Repository.objects.select_related("user__server"),
        name=repo,
        user__name=owner,
    )
    return do_repo_page(request, repo)


def view_repo(request, repo_id):
    """
    Render the repo page given the internal DB id of the repo
    Input:
        request[django.http.HttpRequest]
        repo_id[int]: The internal DB id of the repo
    """
    repo = get_object_or_404(
        models.Repository.objects.select_related("user__server"), pk=repo_id
    )
    return do_repo_page(request, repo)


def view_client(request, client_id):
    """
    View details about a client, along with
    some a list of paginated jobs it has run
    """
    client = get_object_or_404(models.Client, pk=client_id)

    allowed = Permissions.is_allowed_to_see_clients(request.session)
    if not allowed:
        return render(request, "ci/client.html", {"client": None, "allowed": False})

    jobs_list = (
        models.Job.objects.filter(client=client)
        .order_by("-last_modified")
        .select_related(
            "config",
            "event__pull_request",
            "event__base__branch__repository__user",
            "event__head__branch__repository__user",
            "recipe",
        )
    )
    jobs = get_paginated(request, jobs_list)
    data = {
        "client": client,
        "jobs": jobs,
        "running_jobs": client.running_jobs().select_related("recipe", "config"),
        "can_manage": Permissions.can_manage_clients(request.session),
        "allowed": True,
    }
    return render(request, "ci/client.html", data)


def do_branch_page(request, branch):
    """
    Render the branch page given a branch object
    Input:
        request[django.http.HttpRequest]
        branch[models.Branch]
    """
    if request.method != "GET":
        return HttpResponseNotAllowed(["GET"])

    unauthorized = render_unauthorized_repo(request, branch.repository)
    if unauthorized is not None:
        return unauthorized

    causes = []
    if request.GET.get("do_filter", "0") == "0":
        causes = [models.Event.PUSH, models.Event.MANUAL, models.Event.RELEASE]
        form = forms.BranchEventsForm(initial={"filter_events": causes})
    else:
        form = forms.BranchEventsForm(request.GET)
        if form.is_valid():
            causes = [int(c) for c in form.cleaned_data["filter_events"]]

    event_list = EventsStatus.get_default_events_query().filter(
        base__branch=branch, cause__in=causes
    )
    events = get_paginated(request, event_list)
    evs_info = EventsStatus.multiline_events_info(events)
    return render(
        request,
        "ci/branch.html",
        {"form": form, "branch": branch, "events": evs_info, "pages": events},
    )


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
    branch = get_object_or_404(
        q, name=branch, repository__name=repo, repository__user__name=owner
    )
    return do_branch_page(request, branch)


def view_branch(request, branch_id):
    """
    Render the branch page based on a branch id
    Input:
        request[django.http.HttpRequest]
        branch_id[int]: Internal DB id of the branch
    """
    branch = get_object_or_404(
        models.Branch.objects.select_related("repository__user__server"),
        pk=int(branch_id),
    )
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
        raise Http404("Bad username")

    viewable_repos = Permissions.viewable_repos(request.session)
    repos = RepositoryStatus.get_user_repos_with_open_prs_status(
        username, filter_repo_ids=viewable_repos
    )
    pr_ids = []
    for r in repos:
        for pr in r["prs"]:
            pr_ids.append(pr["id"])
    event_list = EventsStatus.get_single_event_for_open_prs(
        pr_ids, filter_repo_ids=viewable_repos
    )
    evs_info = EventsStatus.multiline_events_info(event_list)
    data = {
        "username": username,
        "repos": repos,
        "events": evs_info,
        "update_interval": settings.EVENT_PAGE_UPDATE_INTERVAL,
    }
    return render(request, "ci/user.html", data)


def pr_list(request):
    viewable_repos = Permissions.viewable_repos(request.session)
    pr_list = (
        models.PullRequest.objects.filter(repository__id__in=viewable_repos)
        .order_by("-created")
        .select_related("repository__user__server")
        .order_by("repository__user__name", "repository__name", "number")
    )
    prs = get_paginated(request, pr_list)
    return render(request, "ci/prs.html", {"prs": prs})


def branch_list(request):
    viewable_repos = Permissions.viewable_repos(request.session)
    branch_list = (
        models.Branch.objects.filter(repository__id__in=viewable_repos)
        .exclude(status=models.JobStatus.NOT_STARTED)
        .select_related("repository__user__server")
        .order_by("repository__user__name", "repository__name", "name")
    )
    branches = get_paginated(request, branch_list)
    return render(request, "ci/branches.html", {"branches": branches})


def client_list(request):
    allowed = Permissions.is_allowed_to_see_clients(request.session)
    if not allowed:
        return render(request, "ci/clients.html", {"clients": None, "allowed": False})

    data = {
        "clients": clients_info(),
        "disabled_clients": disabled_clients_info(),
        "can_manage": Permissions.can_manage_clients(request.session),
        "allowed": True,
        "update_interval": settings.HOME_PAGE_UPDATE_INTERVAL,
    }
    return render(request, "ci/clients.html", data)


CLIENT_ACTIONS = ["disable", "disable_immediate", "enable"]


def update_clients(request):
    """
    Disables or enables clients. Only server admins are allowed.
    POST data:
      client_ids: list of models.Client.pk
      action: str: One of CLIENT_ACTIONS
      next: str: Optional local URL to redirect to
    """
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    user = Permissions.client_manager(request.session)
    if user is None:
        return HttpResponseForbidden("Not allowed to manage clients")

    response = clients_redirect(request)
    action = request.POST.get("action")
    if action not in CLIENT_ACTIONS:
        messages.error(request, "Invalid client action")
        return response
    clients = selected_clients(request)
    if not clients:
        messages.error(request, "No clients selected")
        return response

    if action == "enable":
        enable_clients(clients, user)
        messages.info(request, "Enabled %s client(s)" % len(clients))
        return response

    # Every client must be disabled before any job is invalidated, so that
    # an invalidated job can't go to a client that is about to be disabled
    disable_clients(clients, user)
    num_invalidated = 0
    if action == "disable_immediate":
        num_invalidated = invalidate_running_jobs(clients, user)
    # After invalidating, as invalidated jobs are no longer pinned
    num_canceled = cancel_pinned_jobs(clients, user)
    messages.info(
        request,
        "Disabled %s client(s); invalidated %s running job(s); canceled %s pinned job(s)"
        % (len(clients), num_invalidated, num_canceled),
    )
    return response


def clients_redirect(request):
    """
    Redirect to the POSTed "next" URL if it is on this site, otherwise
    to the clients page.
    """
    next_url = request.POST.get("next")
    if next_url and url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return redirect(next_url)
    return redirect("ci:client_list")


def selected_clients(request):
    """
    The existing clients in the POSTed client_ids.
    """
    ids = [int(i) for i in request.POST.getlist("client_ids") if i.isdigit()]
    return sorted_clients(models.Client.objects.filter(pk__in=ids))


def disable_clients(clients, user):
    """
    Disables the clients in a single UPDATE, so they are all disabled at
    once. Clients that are already disabled keep who disabled them and when.
    """
    pks = [c.pk for c in clients if not c.disabled]
    models.Client.objects.filter(pk__in=pks).update(
        disabled=True, disabled_time=timezone.now(), disabled_by=str(user)
    )
    for client in clients:
        logger.info("Client %s: %s disabled by %s" % (client.pk, client, user))


def enable_clients(clients, user):
    models.Client.objects.filter(pk__in=[c.pk for c in clients]).update(
        disabled=False, disabled_time=None, disabled_by=""
    )
    for client in clients:
        logger.info("Client %s: %s enabled by %s" % (client.pk, client, user))


def invalidate_running_jobs(clients, user):
    """
    Invalidates the jobs running on the clients so that other clients can
    run them. Returns the number of jobs invalidated.
    """
    num = 0
    for client in clients:
        for job in client.running_jobs().select_related("event", "recipe"):
            message = "Invalidated because its client was disabled by %s" % user
            logger.info("Job %s: %s: %s: %s" % (job.pk, job, client, message))
            job.set_invalidated(
                message, same_client=False, check_ready=True, changelog_client=client
            )
            num += 1
    return num


def cancel_pinned_jobs(clients, user):
    """
    Cancels the jobs that can only run on the clients, as they won't run
    while the clients are disabled. Returns the number of jobs canceled.
    """
    num = 0
    for client in clients:
        for job in client.pinned_jobs().select_related("event", "recipe"):
            message = (
                "Canceled because it is pinned to a client that was disabled "
                "by %s; it would not run until that client is re-enabled. "
                "Invalidate the job to run it on another client." % user
            )
            logger.info("Job %s: %s: %s: %s" % (job.pk, job, client, message))
            set_job_canceled(job, message, client=client)
            UpdateRemoteStatus.job_complete(job)
            num += 1
    return num


def scheduled_recipes():
    """
    The recipes that the cron scheduler runs
    """
    return models.Recipe.objects.filter(
        active=True, current=True, scheduler__isnull=False, branch__isnull=False
    ).exclude(scheduler="")


def manual_cron(request, recipe_id):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    allowed = Permissions.is_allowed_to_see_clients(request.session)
    if not allowed:
        return HttpResponseForbidden("Not allowed to start manual cron runs")

    q = scheduled_recipes().select_related("repository__user__server")
    r = get_object_or_404(q, pk=recipe_id)

    unauthorized = render_unauthorized_repo(request, r.repository)
    if unauthorized is not None:
        return unauthorized

    user = r.build_user
    branch = r.branch

    latest = user.api().last_sha(
        branch.repository.user.name, branch.repository.name, branch.name
    )
    # likely need to add exception checks for this!
    if latest:
        r.last_scheduled = datetime.now(tz=pytz.UTC)
        r.save()
        mev = ManualEvent.ManualEvent(user, branch, latest, r)
        mev.force = True
        mev.save(update_branch_status=True)

    return redirect("ci:cronjobs")


def cronjobs(request):
    # TODO: make this check for permission to view cron stuff instead
    allowed = Permissions.is_allowed_to_see_clients(request.session)
    if not allowed:
        return render(request, "ci/cronjobs.html", {"recipes": None, "allowed": False})

    recipe_list = scheduled_recipes().order_by("repository__name")
    local_tz = pytz.timezone("US/Mountain")
    for r in recipe_list:
        events = (
            EventsStatus.get_default_events_query()
            .filter(jobs__recipe__filename=r.filename, jobs__recipe__cause=r.cause)
            .order_by("-created")
        )
        r.most_recent_event = events[0] if len(events) > 0 else None

        c = croniter(r.scheduler, start_time=r.last_scheduled.astimezone(local_tz))
        r.next_run_time = c.get_next(datetime)

    # TODO: augment recipes objects with fields that html template will need.
    data = {
        "recipes": recipe_list,
        "allowed": True,
        "update_interval": settings.HOME_PAGE_UPDATE_INTERVAL,
    }
    return render(request, "ci/cronjobs.html", data)


def ready_jobs(request):
    allowed = Permissions.is_allowed_to_see_clients(request.session)
    if not allowed:
        return render(
            request,
            "ci/ready_jobs.html",
            {"allowed": False, "jobs_by_config": None, "num_jobs": None},
        )

    num_jobs = 0
    jobs_by_config = defaultdict(list)
    for job in get_ready_jobs():
        jobs_by_config[str(job.config)].append(job)
        num_jobs += 1

    data = {
        "allowed": True,
        "jobs_by_config": dict(jobs_by_config),
        "num_jobs": num_jobs,
    }
    return render(request, "ci/ready_jobs.html", data)


def clients_info():
    """
    Gets the information on all the currently active, enabled clients.
    Retruns:
      list of dicts containing client information
    """
    sclients = sorted_clients(
        models.Client.objects.exclude(status=models.Client.DOWN).filter(disabled=False)
    )
    active_clients = []  # clients that we've seen in <= 60 s
    inactive_clients = []  # clients that we've seen in > 60 s
    for c in sclients:
        d = {
            "pk": c.pk,
            "ip": c.ip,
            "name": c.name,
            "message": c.status_message,
            "status": c.status_str(),
            "lastseen": TimeUtils.human_time_str(c.last_seen),
        }
        if c.unseen_seconds() > 2 * 7 * 24 * 60 * 60:  # 2 weeks
            # do it like this so that last_seen doesn't get updated
            models.Client.objects.filter(pk=c.pk).update(status=models.Client.DOWN)
        elif c.unseen_seconds() > 160:
            d["status_class"] = "client_NotSeen"
            inactive_clients.append(d)
        else:
            d["status_class"] = "client_%s" % c.status_slug()
            active_clients.append(d)
    clients = []  # sort these so that active clients (seen in < 60 s) are first
    for d in active_clients:
        clients.append(d)
    for d in inactive_clients:
        clients.append(d)
    return clients


def disabled_clients_info():
    """
    Gets the information on all the disabled clients, including those
    that are down, so that they can be found and enabled again.
    Returns:
      list of dicts containing client information
    """
    clients = sorted_clients(models.Client.objects.filter(disabled=True))
    running_jobs = models.Job.objects.filter(
        client__in=clients, complete=False, status=models.JobStatus.RUNNING
    )
    running_job_by_client = {job.client_id: job for job in running_jobs}

    info = []
    for c in clients:
        d = {
            "pk": c.pk,
            "ip": c.ip,
            "name": c.name,
            "disabled_by": c.disabled_by,
            "disabled_time": "",
            "lastseen": TimeUtils.human_time_str(c.last_seen),
            "running_job_url": None,
            # Disabled without a running job means it is safe to update
            "state": "Disabled",
        }
        if c.disabled_time:
            d["disabled_time"] = TimeUtils.human_time_str(c.disabled_time)
        job = running_job_by_client.get(c.pk)
        if job:
            d["running_job_url"] = reverse("ci:view_job", args=[job.pk])
            d["state"] = "Finishing job %s" % job.pk
        info.append(d)
    return info


def event_list(request):
    viewable_repos = Permissions.viewable_repos(request.session)
    event_list = EventsStatus.get_default_events_query(filter_repo_ids=viewable_repos)
    events = get_paginated(request, event_list)
    evs_info = EventsStatus.multiline_events_info(events)
    return render(request, "ci/events.html", {"events": evs_info, "pages": events})


def sha_events(request, owner, repo, sha):
    repo = get_object_or_404(models.Repository.objects, name=repo, user__name=owner)

    unauthorized = render_unauthorized_repo(request, repo)
    if unauthorized is not None:
        return unauthorized

    event_q = models.Event.objects.filter(
        head__branch__repository=repo, head__sha__startswith=sha
    )
    # The base repository of an event can differ from the head repository
    viewable_repos = Permissions.viewable_repos(request.session)
    event_list = EventsStatus.get_default_events_query(
        event_q, filter_repo_ids=viewable_repos
    )
    events = get_paginated(request, event_list)
    evs_info = EventsStatus.multiline_events_info(events)
    return render(
        request,
        "ci/events.html",
        {"events": evs_info, "pages": events, "sha": sha, "repo": repo},
    )


def recipe_crons(request, recipe_id):
    q = models.Recipe.objects.select_related("repository")
    recipe = get_object_or_404(q, pk=recipe_id)

    unauthorized = render_unauthorized_repo(request, recipe.repository)
    if unauthorized is not None:
        return unauthorized

    # Recipes are matched by filename across versions, which could
    # span repositories, so only include events the user can see
    viewable_repos = Permissions.viewable_repos(request.session)
    event_list = (
        EventsStatus.get_default_events_query(filter_repo_ids=viewable_repos)
        .filter(
            jobs__recipe__filename=recipe.filename,
            jobs__recipe__cause=recipe.cause,
            jobs__recipe__scheduler__isnull=False,
        )
        .exclude(jobs__recipe__scheduler="")
    )
    total = 0
    count = 0
    qs = models.Job.objects.filter(
        recipe__filename=recipe.filename,
        recipe__cause=recipe.cause,
        status=models.JobStatus.SUCCESS,
        event__base__branch__repository__id__in=viewable_repos,
    )
    for job in qs.all():
        total += job.seconds.total_seconds()
        count += 1
    if count:
        total /= count
    events = get_paginated(request, event_list)
    evs_info = EventsStatus.multiline_events_info(events)
    avg = timedelta(seconds=total)
    data = {
        "recipe": recipe,
        "events": evs_info,
        "average_time": avg,
        "pages": events,
    }
    return render(request, "ci/recipe_crons.html", data)


def invalidate_job(
    request,
    job,
    message,
    same_client=False,
    client=None,
    check_ready=True,
    changelog_event=None,
):
    """
    Convience function to invalidate a job and show a message to the user.
    Input:
      request: django.http.HttpRequest
      job. models.Job
      same_client: bool
      changelog_event: models.Event: Event to link to in the change log
    """
    job.set_invalidated(
        message, same_client, client, check_ready, changelog_event=changelog_event
    )
    messages.info(request, "Job results invalidated for {}".format(job))


def invalidate_event(request, event_id):
    """
    Invalidate all the jobs of an event.
    The user must be signed in.
    Input:
      request: django.http.HttpRequest
      event_id. models.Event.pk: PK of the event to be invalidated
    Return: django.http.HttpResponse based object
    """
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    q = models.Event.objects.select_related("base__branch__repository")
    ev = get_object_or_404(q, pk=event_id)

    unauthorized = render_unauthorized_repo(request, ev.base.repo())
    if unauthorized is not None:
        return unauthorized

    allowed = Permissions.can_invalidate(request.session, ev)
    if not allowed:
        messages.error(
            request,
            "You need to be signed in and have write access (or be the pull request author and a collaborator) to invalidate results.",
        )
        return redirect("ci:view_event", event_id=ev.pk)
    if not Permissions.can_see_event_results(request.session, ev):
        messages.error(
            request,
            "You are not allowed to invalidate jobs of private recipes on this event.",
        )
        return redirect("ci:view_event", event_id=ev.pk)

    signed_in_user = ev.base.server().signed_in_user(request.session)
    comment = request.POST.get("comment")
    logger.info("Event {}: {} invalidated by {}".format(ev.pk, ev, signed_in_user))
    message = "Parent event invalidated by %s" % signed_in_user
    if comment:
        message += " with comment: %s" % comment

    post_to_pr = request.POST.get("post_to_pr") == "on"
    if post_to_pr:
        post_event_change_to_pr(
            request, ev, "invalidated", escape(comment), signed_in_user
        )

    same_client = request.POST.get("same_client") == "on"
    for job in ev.jobs.select_related("client"):
        # Don't pin a job to a disabled client, it wouldn't run
        pin = pinned_client(job, same_client, None)
        job_same_client = same_client
        if pin and pin.disabled:
            job_same_client = False
            messages.warning(
                request,
                "Client %s is disabled; job %s can run on any client" % (pin, job),
            )
        invalidate_job(
            request,
            job,
            message,
            job_same_client,
            check_ready=False,
            changelog_event=ev,
        )
    # Only do this once so that we get the job dependencies setup correctly.
    ev.make_jobs_ready()

    return redirect("ci:view_event", event_id=ev.pk)


def prioritize_job(request, job, message, changelog_event=None):
    """
    Convience function to prioritized a job and show a message to the user.
    Input:
      request: django.http.HttpRequest
      job: models.Job
      message: str
      changelog_event: models.Event: Event to link to in the change log
    """
    job.set_prioritized(message, changelog_event)
    messages.info(request, f"Job {job} prioritized")


def prioritize_event(request, event_id):
    """
    Prioritize all the jobs of an event.
    The user must be signed in.
    Input:
      request: django.http.HttpRequest
      event_id. models.Event.pk: PK of the event to be invalidated
    Return: django.http.HttpResponse based object
    """
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    q = models.Event.objects.select_related("base__branch__repository")
    ev = get_object_or_404(q, pk=event_id)

    unauthorized = render_unauthorized_repo(request, ev.base.repo())
    if unauthorized is not None:
        return unauthorized

    if not Permissions.is_server_admin(request.session, ev.base.server()):
        messages.error(request, "You are not authorized to prioritize events.")
        return redirect("ci:view_event", event_id=ev.pk)

    user = ev.base.server().signed_in_user(request.session)
    comment = request.POST.get("comment")
    logger.info(f"Event {ev.pk}: {ev} prioritized by {user}")
    message = f"Parent event prioritized by {user}"
    if comment:
        message += " with comment: %s" % comment

    for job in ev.jobs.all():
        prioritize_job(request, job, message, changelog_event=ev)

    return redirect("ci:view_event", event_id=ev.pk)


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
        additional = ""
        if comment:
            additional = "\n\n%s" % comment
        abs_job_url = request.build_absolute_uri(reverse("ci:view_job", args=[job.pk]))
        pr_message = "Job [%s](%s) on %s : %s by @%s%s" % (
            job.unique_name(),
            abs_job_url,
            job.event.head.short_sha(),
            action,
            signed_in_user,
            additional,
        )
        tasks.pr_comment.enqueue(
            job.event.build_user.pk, job.event.comments_url, pr_message
        )


def pinned_client(job, same_client, client):
    """
    The client that an invalidated job would be pinned to, if any.
    """
    if client:
        return client
    if same_client:
        return job.client
    return None


def invalidate(request, job_id):
    """
    Invalidate the results of a Job.
    The user must be signed in.
    Input:
      request: django.http.HttpRequest
      job_id: models.Job.pk
    """
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    q = models.Job.objects.select_related("event__base__branch__repository")
    job = get_object_or_404(q, pk=job_id)

    unauthorized = render_unauthorized_repo(request, job.event.base.repo())
    if unauthorized is not None:
        return unauthorized

    perms = Permissions.job_permissions(request.session, job)
    if not perms["can_invalidate"]:
        raise PermissionDenied("You are not allowed to invalidate results.")
    same_client = request.POST.get("same_client") == "on"
    selected_client = None
    if perms["can_see_client"]:
        selected_client = request.POST.get("client_list")
    comment = request.POST.get("comment")
    post_to_pr = request.POST.get("post_to_pr") == "on"
    client = None
    if selected_client:
        try:
            client = models.Client.objects.get(pk=int(selected_client))
            same_client = True
        except:
            pass
    pin = pinned_client(job, same_client, client)
    if pin and pin.disabled:
        messages.error(request, "Client %s is disabled; can't run the job on it" % pin)
        return redirect("ci:view_job", job_id=job.pk)

    signed_in_user = job.event.base.server().signed_in_user(request.session)
    message = "Invalidated by %s" % signed_in_user
    if comment:
        message += "\nwith comment: %s" % comment

    if post_to_pr:
        post_job_change_to_pr(
            request, job, "invalidated", escape(comment), signed_in_user
        )

    logger.info(
        "Job {}: {} on {} invalidated by {}".format(
            job.pk, job, job.recipe.repository, signed_in_user
        )
    )
    invalidate_job(request, job, message, same_client, client)
    return redirect("ci:view_job", job_id=job.pk)


def prioritize(request, job_id):
    """
    Prioritize a Job.
    The user must be signed in.
    Input:
      request: django.http.HttpRequest
      job_id: models.Job.pk
    """
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    q = models.Job.objects.select_related("event__base__branch__repository")
    job = get_object_or_404(q, pk=job_id)

    unauthorized = render_unauthorized_repo(request, job.event.base.repo())
    if unauthorized is not None:
        return unauthorized

    if not Permissions.is_server_admin(request.session, job.event.base.server()):
        raise PermissionDenied("You are not allowed to prioritize jobs.")

    user = job.event.base.server().signed_in_user(request.session)
    comment = request.POST.get("comment")
    message = f"Prioritized by {user}"
    if comment:
        message += "\nwith comment: %s" % comment

    logger.info(
        "Job {}: {} on {} prioritized by {}".format(
            job.pk, job, job.recipe.repository, user
        )
    )
    prioritize_job(request, job, message)
    return redirect("ci:view_job", job_id=job.pk)


def sort_recipes_key(entry):
    return str(entry[0].repository)


def view_profile(request, server_type, server_name):
    """
    View the recipes that the user owns
    """
    server = get_object_or_404(
        models.GitServer, host_type=server_type, name=server_name
    )
    user = server.signed_in_user(request.session)
    if not user:
        request.session["source_url"] = request.build_absolute_uri()
        return redirect(server.api().sign_in_url())

    recipes = (
        models.Recipe.objects.filter(build_user=user, current=True)
        .order_by("repository__name", "cause", "branch__name", "name")
        .select_related("branch", "repository__user")
        .prefetch_related("build_configs", "depends_on")
    )
    recipe_data = []
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

    return render(
        request,
        "ci/profile.html",
        {
            "user": user,
            "recipes_by_repo": recipe_data,
        },
    )


def set_job_active(request, job, user):
    """
    Sets an inactive job to active and check to see if it is ready to run
    Returns a bool indicating if it changed the job.
    """
    if job.active:
        return False

    job.active = True
    job.event.complete = False
    job.set_status(
        models.JobStatus.NOT_STARTED, calc_event=True
    )  # will save job and event
    message = "Activated by %s" % user
    models.JobChangeLog.objects.create(job=job, message=message)
    messages.info(request, "Job %s activated" % job)
    return True


def activate_event(request, event_id):
    """
    Endpoint for activating all jobs on an event
    """
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    q = models.Event.objects.select_related("base__branch__repository")
    ev = get_object_or_404(q, pk=event_id)

    unauthorized = render_unauthorized_repo(request, ev.base.repo())
    if unauthorized is not None:
        return unauthorized

    jobs = ev.jobs.filter(active=False).order_by("-created")
    if jobs.count() == 0:
        messages.info(request, "No jobs to activate")
        return redirect("ci:view_event", event_id=ev.pk)

    repo = jobs.first().recipe.repository
    user = repo.server().signed_in_user(request.session)
    if not user:
        raise PermissionDenied("You need to be signed in to activate jobs")

    # Write access is enough to activate the whole event, even if some
    # of its jobs are from private recipes that the user can't see
    allowed = Permissions.has_write_access(
        request.session, ev.build_user, repo, user=user
    )
    if allowed:
        activated_jobs = []
        for j in jobs.all():
            if set_job_active(request, j, user):
                activated_jobs.append(j)
        for j in activated_jobs:
            j.init_pr_status()
        ev.make_jobs_ready()
    else:
        raise PermissionDenied(
            "Activate event: {} does NOT have write access to {}".format(user, repo)
        )

    return redirect("ci:view_event", event_id=ev.pk)


def activate_job(request, job_id):
    """
    Endpoint for activating a job
    """
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    q = models.Job.objects.select_related("event__base__branch__repository")
    job = get_object_or_404(q, pk=job_id)

    unauthorized = render_unauthorized_repo(request, job.event.base.repo())
    if unauthorized is not None:
        return unauthorized

    server = job.recipe.repository.server()
    user = server.signed_in_user(request.session)
    if not user:
        raise PermissionDenied("You need to be signed in to activate a job")

    perms = Permissions.job_permissions(request.session, job)
    if perms["can_activate"]:
        if set_job_active(request, job, user):
            job.init_pr_status()
        job.event.make_jobs_ready()
    else:
        raise PermissionDenied(
            "Activate job: {} is not allowed to activate jobs on {}".format(
                user, job.recipe.repository
            )
        )

    return redirect("ci:view_job", job_id=job.pk)


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
        additional = ""
        if comment:
            additional = "\n\n%s" % comment
        abs_ev_url = request.build_absolute_uri(reverse("ci:view_event", args=[ev.pk]))
        pr_message = "All [jobs](%s) on %s : %s by @%s%s" % (
            abs_ev_url,
            ev.head.short_sha(),
            action,
            signed_in_user,
            additional,
        )
        tasks.pr_comment.enqueue(ev.build_user.pk, ev.comments_url, pr_message)


def cancel_event(request, event_id):
    """
    Cancel all jobs attached to an event
    """
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    q = models.Event.objects.select_related("base__branch__repository")
    ev = get_object_or_404(q, pk=event_id)

    unauthorized = render_unauthorized_repo(request, ev.base.repo())
    if unauthorized is not None:
        return unauthorized

    allowed = Permissions.can_cancel(
        request.session, ev
    ) and Permissions.can_see_event_results(request.session, ev)
    if not allowed:
        messages.error(request, "You are not allowed to cancel this event")
        return redirect("ci:view_event", event_id=ev.pk)

    signed_in_user = ev.base.server().signed_in_user(request.session)
    comment = request.POST.get("comment")
    post_to_pr = request.POST.get("post_to_pr") == "on"
    message = "Parent event canceled by %s" % signed_in_user
    if comment:
        message += " with comment: %s" % comment
    if post_to_pr:
        post_event_change_to_pr(
            request, ev, "canceled", escape(comment), signed_in_user
        )

    event.cancel_event(ev, message, True, changelog_event=ev)
    logger.info("Event {}: {} canceled by {}".format(ev.pk, ev, signed_in_user))
    messages.info(request, "Event {} canceled".format(ev))

    return redirect("ci:view_event", event_id=ev.pk)


def set_job_canceled(
    job, msg=None, status=models.JobStatus.CANCELED, client=None, event=None
):
    job.complete = True
    job.set_status(status, calc_event=True)  # This will save the job
    if msg:
        models.JobChangeLog.objects.create(
            job=job, message=msg, client=client, event=event
        )


def cancel_job(request, job_id):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    q = models.Job.objects.select_related("event__base__branch__repository")
    job = get_object_or_404(q, pk=job_id)

    unauthorized = render_unauthorized_repo(request, job.event.base.repo())
    if unauthorized is not None:
        return unauthorized

    perms = Permissions.job_permissions(request.session, job)
    if not perms["can_cancel"]:
        return HttpResponseForbidden("Not allowed to cancel this job")

    signed_in_user = job.event.base.server().signed_in_user(request.session)
    message = "Canceled by %s" % signed_in_user
    comment = request.POST.get("comment")

    post_to_pr = request.POST.get("post_to_pr") == "on"
    if post_to_pr:
        post_job_change_to_pr(request, job, "canceled", escape(comment), signed_in_user)

    if comment:
        message += "\nwith comment: %s" % comment
    set_job_canceled(job, message)
    UpdateRemoteStatus.job_complete(job)
    logger.info(
        "Job {}: {} on {} canceled by {}".format(
            job.pk, job, job.recipe.repository, signed_in_user
        )
    )
    messages.info(request, "Job {} canceled".format(job))
    return redirect("ci:view_job", job_id=job.pk)


def mooseframework(request):
    """
    This produces a very basic set of status reports for MOOSE, its branches and
    its open PRs.
    Intended to be included on mooseframework.org
    """
    message = ""
    data = None
    try:
        repo = models.Repository.objects.get(
            user__name="idaholab",
            name="moose",
            user__server__host_type=settings.GITSERVER_GITHUB,
        )
    except models.Repository.DoesNotExist:
        return HttpResponse("Moose not available")

    try:
        master = repo.branches.get(name="master")
        devel = repo.branches.get(name="devel")
    except models.Branch.DoesNotExist:
        return HttpResponse("Branches not there")

    data = {"master_status": master.status_slug()}
    data["master_url"] = request.build_absolute_uri(
        reverse(
            "ci:view_branch",
            args=[
                master.pk,
            ],
        )
    )
    data["devel_status"] = devel.status_slug()
    data["devel_url"] = request.build_absolute_uri(
        reverse(
            "ci:view_branch",
            args=[
                devel.pk,
            ],
        )
    )
    prs = models.PullRequest.objects.filter(repository=repo, closed=False).order_by(
        "number"
    )
    pr_data = []
    for pr in prs:
        d = {
            "number": pr.number,
            "url": request.build_absolute_uri(
                reverse(
                    "ci:view_pr",
                    args=[
                        pr.pk,
                    ],
                )
            ),
            "status": pr.status_slug(),
        }
        pr_data.append(d)
    data["prs"] = pr_data

    return render(
        request,
        "ci/mooseframework.html",
        {
            "status": data,
            "message": message,
        },
    )


def scheduled_events(request):
    """
    List schedule events
    """
    viewable_repos = Permissions.viewable_repos(request.session)
    event_list = EventsStatus.get_default_events_query(filter_repo_ids=viewable_repos)
    event_list = event_list.filter(cause=models.Event.MANUAL)
    events = get_paginated(request, event_list)
    evs_info = EventsStatus.multiline_events_info(events)
    return render(request, "ci/scheduled.html", {"events": evs_info, "pages": events})


def get_branch_status(branch):
    """
    Returns an SVG image of the status of a branch.
    Input:
        branch[models.Branch]: Branch to get the image for
    """
    if branch.status == models.JobStatus.NOT_STARTED:
        raise Http404("Branch not active")

    m = {
        models.JobStatus.SUCCESS: "CIVET-passed-green.svg",
        models.JobStatus.FAILED: "CIVET-failed-red.svg",
        models.JobStatus.FAILED_OK: "CIVET-failed_but_allowed-orange.svg",
        models.JobStatus.RUNNING: "CIVET-running-yellow.svg",
        models.JobStatus.CANCELED: "CIVET-canceled-lightgrey.svg",
    }
    static_file = m[branch.status]
    this_dir = os.path.dirname(__file__)
    full_path = os.path.join(
        this_dir, "static", "third_party", "shields.io", static_file
    )
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
        return HttpResponseNotAllowed(["GET"])

    branch_obj = get_object_or_404(
        models.Branch.objects,
        repository__user__name=owner,
        repository__name=repo,
        name=branch,
    )
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
        return HttpResponseNotAllowed(["GET"])

    branch = get_object_or_404(models.Branch.objects, pk=int(branch_id))
    return get_branch_status(branch)
