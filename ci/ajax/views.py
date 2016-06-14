from django.utils import timezone
from django.http import JsonResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, render
from django.core.urlresolvers import reverse
from ci import models
import datetime
from ci import Permissions, TimeUtils, EventsStatus, RepositoryStatus
import logging
logger = logging.getLogger('ci')

def get_result_output(request):
  if 'result_id' not in request.GET:
    return HttpResponseBadRequest('Missing parameter')

  result_id = request.GET['result_id']

  result = get_object_or_404(models.StepResult, pk=result_id)
  ret = Permissions.can_see_results(request, result.job.recipe)
  if ret:
    return ret

  return JsonResponse({'contents': result.clean_output()})

def event_update(request, event_id):
  ev = get_object_or_404(models.Event, pk=event_id)
  ev_data = {'id': ev.pk,
      'complete': ev.complete,
      'last_modified': TimeUtils.display_time_str(ev.last_modified),
      'created': TimeUtils.display_time_str(ev.created),
      'status': ev.status_slug(),
    }
  ev_data['events'] = EventsStatus.events_info([ev])
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
  pr_data['events'] = EventsStatus.events_info(pr.events.all(), events_url=True)
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
  repos_data = RepositoryStatus.main_repos_status(dt)
  # we also need to check if a PR closed recently
  closed = []
  for pr in models.PullRequest.objects.filter(closed=True, last_modified__gte=dt).values('id').all():
    closed.append({'id': pr['id']})

  einfo = EventsStatus.all_events_info(last_modified=dt)
  return JsonResponse({'repo_status': repos_data, 'closed': closed, 'last_request': this_request, 'events': einfo, 'limit': limit })

def main_update_html(request):
  """
  Used for testing the update with debug toolbar.
  """
  response = main_update(request)
  return render(request, 'ci/ajax_test.html', {'content': response.content})

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
  ret = Permissions.can_see_results(request, job.recipe)
  if ret:
    return ret


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
