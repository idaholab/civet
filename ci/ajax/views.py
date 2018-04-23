
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

from __future__ import unicode_literals
from django.utils import timezone
from django.http import JsonResponse, HttpResponseBadRequest, HttpResponseForbidden
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from ci import models, views
import datetime
from ci import Permissions, TimeUtils, EventsStatus, RepositoryStatus
import logging
logger = logging.getLogger('ci')

def get_result_output(request):
    if 'result_id' not in request.GET:
        return HttpResponseBadRequest('Missing parameter')

    result_id = request.GET['result_id']

    result = get_object_or_404(models.StepResult, pk=result_id)
    if not Permissions.can_see_results(request.session, result.job.recipe):
        return HttpResponseForbidden("Can't see results")

    return JsonResponse({'contents': result.clean_output()})

def event_update(request, event_id):
    ev = get_object_or_404(models.Event, pk=event_id)
    ev_data = {'id': ev.pk,
        'complete': ev.complete,
        'last_modified': TimeUtils.display_time_str(ev.last_modified),
        'created': TimeUtils.display_time_str(ev.created),
        'status': ev.status_slug(),
      }
    ev_data['events'] = EventsStatus.multiline_events_info([ev])
    return JsonResponse(ev_data)

def pr_update(request, pr_id):
    pr = get_object_or_404(models.PullRequest, pk=pr_id)
    closed = 'Open'
    if pr.closed:
        closed = 'Closed'
    pr_data = {'id': pr.pk,
        'closed': closed,
        'last_modified': TimeUtils.display_time_str(pr.last_modified),
        'created': TimeUtils.display_time_str(pr.created),
        'status': pr.status_slug(),
      }
    pr_data['events'] = EventsStatus.multiline_events_info(pr.events.all(), events_url=True)
    return JsonResponse(pr_data)

def main_update(request):
    """
    Get the updates for the main page.
    """
    if 'last_request' not in request.GET or 'limit' not in request.GET:
        return HttpResponseBadRequest('Missing parameters')

    this_request = TimeUtils.get_local_timestamp()
    limit = int(request.GET['limit'])
    last_request = int(float(request.GET['last_request'])) # in case it has decimals
    dt = timezone.localtime(timezone.make_aware(datetime.datetime.utcfromtimestamp(last_request)))
    repos_data, einfo, default = views.get_user_repos_info(request, limit=limit, last_modified=dt)
    # we also need to check if a PR closed recently
    closed = []
    for pr in models.PullRequest.objects.filter(closed=True, last_modified__gte=dt).values('id').all():
        closed.append({'id': pr['id']})

    return JsonResponse({'repo_status': repos_data,
        'closed': closed,
        'last_request': this_request,
        'events': einfo,
        'limit': limit,
        })

def main_update_html(request):
    """
    Used for testing the update with debug toolbar.
    """
    response = main_update(request)
    return render(request, 'ci/ajax_test.html', {'content': response.content})

def repo_update(request):
    """
    Get the updates for the repo page.
    """
    if 'last_request' not in request.GET or 'limit' not in request.GET or 'repo_id' not in request.GET:
        return HttpResponseBadRequest('Missing parameters')

    this_request = TimeUtils.get_local_timestamp()
    repo_id = int(request.GET['repo_id'])
    limit = int(request.GET['limit'])
    last_request = int(float(request.GET['last_request'])) # in case it has decimals
    dt = timezone.localtime(timezone.make_aware(datetime.datetime.utcfromtimestamp(last_request)))
    repo = get_object_or_404(models.Repository, pk=repo_id)
    repos_status = RepositoryStatus.filter_repos_status([repo.pk], last_modified=dt)
    event_q = EventsStatus.get_default_events_query()
    event_q = event_q.filter(base__branch__repository=repo)[:limit]
    events_info = EventsStatus.multiline_events_info(event_q, last_modified=dt)
    # we also need to check if a PR closed recently
    closed = []
    for pr in models.PullRequest.objects.filter(repository=repo, closed=True, last_modified__gte=dt).values('id').all():
        closed.append({'id': pr['id']})

    return JsonResponse({'repo_status': repos_status,
        'closed': closed,
        'last_request': this_request,
        'events': events_info,
        'limit': limit,
        })

def job_results(request):
    """
    Returns the job results and job info in JSON.
    GET parameters:
      job_id: The pk of the job
      last_request: A timestamp of when client last requested this information. If the job
        hasn't been updated since that time we don't have to send as much information.
    """
    if 'last_request' not in request.GET or 'job_id' not in request.GET:
        return HttpResponseBadRequest('Missing parameters')

    this_request = TimeUtils.get_local_timestamp()
    job_id = int(request.GET['job_id'])
    last_request = int(float(request.GET['last_request'])) # in case it has decimals
    dt = timezone.localtime(timezone.make_aware(datetime.datetime.utcfromtimestamp(last_request)))
    job = get_object_or_404(models.Job, pk=job_id)
    if not Permissions.can_see_results(request.session, job.recipe):
        return HttpResponseForbidden("Can't see results")

    job_info = {
        'id': job.pk,
        'complete': job.complete,
        'status': job.status_slug(),
        'runtime': str(job.seconds),
        'ready': job.ready,
        'invalidated': job.invalidated,
        'active': job.active,
        'last_modified': TimeUtils.display_time_str(job.last_modified),
        'created': TimeUtils.display_time_str(job.created),
        'client_name': '',
        'client_url': '',
        'recipe_repo_sha': job.recipe_repo_sha[:6],
        'recipe_sha': job.recipe.filename_sha[:6],
        }

    if job.last_modified < dt:
        # always return the basic info since we need to update the
        # "natural" time
        return JsonResponse({'job_info': job_info, 'results': [], 'last_request': this_request})

    if job.client:
        can_see_client = Permissions.is_allowed_to_see_clients(request.session)
        if can_see_client:
            job_info['client_name'] = job.client.name
            job_info['client_url'] = reverse('ci:view_client', args=[job.client.pk,])

    result_info = []

    for result in job.step_results.all():
        if dt > result.last_modified:
            continue
        exit_status = ''
        if result.complete:
            exit_status = result.exit_status
        info = {'id': result.id,
            'name': result.name,
            'runtime': str(result.seconds),
            'exit_status': exit_status,
            'output': result.clean_output(),
            'status': result.status_slug(),
            'running': result.status != models.JobStatus.NOT_STARTED,
            'complete': result.complete,
            'output_size': result.output_size(),
            }
        result_info.append(info)

    return JsonResponse({'job_info': job_info, 'results': result_info, 'last_request': this_request})

def job_results_html(request):
    """
    Used for testing the update with debug toolbar.
    """
    response = job_results(request)
    return render(request, 'ci/ajax_test.html', {'content': response.content})


def clients_update(request):
    """
    Get the updates for the clients page.
    """
    allowed = Permissions.is_allowed_to_see_clients(request.session)
    if not allowed:
        return HttpResponseBadRequest('Not allowed')
    clients = views.clients_info()
    return JsonResponse({ 'clients': clients })

def repo_branches_status(request, owner, repo):
    """
    Returns JSON of the status of the branches on a repo.

    This just returns a status, name, url for each active branch.
    Input:
      user: str: Name of the owner of the repo
      repo: str: Name of the repo
    """
    repo = get_object_or_404(models.Repository, user__name=owner, name=repo)
    branches = repo.branches.exclude(status=models.JobStatus.NOT_STARTED).all()
    branch_data = []
    for branch in branches:
        branch_data.append({"status": branch.status_slug(),
            "name": branch.name,
            "url": request.build_absolute_uri(reverse("ci:view_branch", args=[branch.pk,])),
            })

    return JsonResponse({"branches": branch_data})

def repo_prs_status(request, owner, repo):
    """
    Returns JSON of the status of the open PRs on a repo.

    This just returns a status, PR number, url for each open PR
    Input:
      user: str: Name of the owner of the repo
      repo: str: Name of the repo
    """
    repo = get_object_or_404(models.Repository, user__name=owner, name=repo)
    prs = models.PullRequest.objects.filter(repository=repo, closed=False).order_by('number')
    pr_data = []
    for pr in prs.all():
        pr_data.append({"number": pr.number,
            "url": request.build_absolute_uri(reverse("ci:view_pr", args=[pr.pk,])),
            "status": pr.status_slug(),
            })
    return JsonResponse({"prs": pr_data})

def user_open_prs(request, username):
    """
    Get the updates for the main page.
    """
    users = models.GitUser.objects.filter(name=username)
    if users.count() == 0:
        return HttpResponseBadRequest('Bad username')

    if 'last_request' not in request.GET:
        return HttpResponseBadRequest('Missing parameters')

    this_request = TimeUtils.get_local_timestamp()
    last_request = int(float(request.GET['last_request'])) # in case it has decimals
    dt = timezone.localtime(timezone.make_aware(datetime.datetime.utcfromtimestamp(last_request)))
    repos = RepositoryStatus.get_user_repos_with_open_prs_status(username)
    repo_ids = []
    pr_ids = []
    for r in repos:
        repo_ids.append(r["id"])
        for pr in r["prs"]:
            pr_ids.append(pr["id"])
    event_list = EventsStatus.get_single_event_for_open_prs(pr_ids)
    evs_info = EventsStatus.multiline_events_info(event_list)
    ev_ids = []
    for e in evs_info:
        ev_ids.append(e["id"])
    # Now get the changed ones
    repos = RepositoryStatus.get_user_repos_with_open_prs_status(username, dt)
    evs_info = EventsStatus.multiline_events_info(event_list, dt)

    data = {'repos': repo_ids,
        'prs': pr_ids,
        'events': ev_ids,
        'repo_status': repos,
        'closed': [],
        'last_request': this_request,
        'changed_events': evs_info,
        }
    return JsonResponse(data)
