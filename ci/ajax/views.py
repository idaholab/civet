from django.conf import settings
from django.utils import timezone
from django.http import JsonResponse, HttpResponseBadRequest, HttpResponseForbidden
from django.shortcuts import get_object_or_404, render
from django.core.urlresolvers import reverse
from ci import models
from ci.recipe import file_utils
from ci import views
import os, datetime, math
import logging
logger = logging.getLogger('ci')

def get_local_timestamp():
  return math.floor((timezone.localtime(timezone.now()) - timezone.make_aware(datetime.datetime.fromtimestamp(0))).total_seconds())

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
      auth = signed_in.server.auth().start_session_for_user(creator)
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

def events_info(events, event_url=False, last_modified=None):
  event_info = []
  for ev in events:
    if last_modified and ev.last_modified <= last_modified:
      continue

    info = { 'id': ev.pk,
        'status': ev.status_slug(),
        'last_modified': views.display_time_str(ev.last_modified),
        'sort_time': views.sortable_time_str(ev.created),
        }
    desc = '<a href="{}">{}</a> '.format(reverse("ci:view_repo", args=[ev.base.branch.repository.pk]), ev.base.branch.repository.name)
    ev_desc = ''
    if ev.description:
      ev_desc = ': {}'.format(ev.description)

    if event_url:
      desc += '<a href="{}">{}{}</a>'.format(reverse("ci:view_event", args=[ev.pk]), ev, ev_desc)
    elif ev.pull_request:
      desc += '<a href="{}">{}{}</a>'.format(reverse("ci:view_pr", args=[ev.pull_request.pk]), ev.pull_request, ev_desc)
    else:
      desc += '<a href="{}">{}{}</a>'.format(reverse("ci:view_event", args=[ev.pk]), ev.base.branch.name, ev_desc)

    info['description'] = desc
    job_info = []
    for job_group in ev.get_sorted_jobs():
      job_group_info = []
      for job in job_group:
        html = '<a href="{}">{}'.format(reverse("ci:view_job", args=[job.pk]), job.recipe.display_name)
        if int(job.seconds.total_seconds()) != 0:
          html += '<br/>{}'.format(job.seconds)
        html += '</a>'
        failed_result = job.failed_result()
        if failed_result:
          html += '<br/>{}'.format(failed_result.name)

        if job.invalidated:
          html += '<br/>(Invalidated)'

        jinfo = { 'id': job.pk,
            'status': job.status_slug(),
            'info': html,
            }
        job_group_info.append(jinfo)
      job_info.append(job_group_info)
    info['job_groups'] = job_info

    event_info.append(info)

  return event_info

def event_update(request, event_id):
  ev = get_object_or_404(models.Event, pk=event_id)
  ev_data = {'id': ev.pk,
      'complete': ev.complete,
      'last_modified': views.display_time_str(ev.last_modified),
      'created': views.display_time_str(ev.created),
      'status': ev.status_slug(),
    }
  ev_data['events'] = events_info([ev], event_url=True)
  return JsonResponse(ev_data)

def pr_update(request, pr_id):
  pr = get_object_or_404(models.PullRequest, pk=pr_id)
  closed = 'Open'
  if pr.closed:
    closed = 'Closed'
  pr_data = {'id': pr.pk,
      'closed': closed,
      'last_modified': views.display_time_str(pr.last_modified),
      'created': views.display_time_str(pr.created),
      'status': pr.status_slug(),
    }
  pr_data['events'] = events_info(pr.events.all(), event_url=True)
  return JsonResponse(pr_data)

def main_update(request):
  """
  Get the updates for the main page.
  """
  if 'last_request' not in request.GET or 'limit' not in request.GET:
    return HttpResponseBadRequest('Missing parameters')

  this_request = get_local_timestamp()
  limit = int(request.GET['limit'])
  last_request = int(float(request.GET['last_request'])) # in case it has decimals
  dt = timezone.localtime(timezone.make_aware(datetime.datetime.utcfromtimestamp(last_request)))
  repos_data = views.get_repos_status(dt)
  # we also need to check if a PR closed recently
  closed = []
  for pr in models.PullRequest.objects.filter(closed=True, last_modified__gte=dt).values('id').all():
    closed.append({'id': pr['id']})

  events = views.get_default_events_query()[:limit]
  einfo = events_info(events, last_modified=dt)
  return JsonResponse({'repo_status': repos_data, 'closed': closed, 'last_request': this_request, 'events': einfo, 'limit': limit })

def main_update_html(request):
  """
  Used for testing the update with debug toolbar.
  """
  response = main_update(request)
  return render(request, 'ci/ajax_test.html', {'content': response.content})

def job_results(request):
  if 'last_request' not in request.GET or 'job_id' not in request.GET:
    return HttpResponseBadRequest('Missing parameters')

  this_request = get_local_timestamp()
  job_id = int(request.GET['job_id'])
  last_request = int(float(request.GET['last_request'])) # in case it has decimals
  dt = timezone.localtime(timezone.make_aware(datetime.datetime.utcfromtimestamp(last_request)))
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
      'invalidated': job.invalidated,
      'last_modified': views.display_time_str(job.last_modified),
      }

  can_see_client = views.is_allowed_to_see_clients(request.session)
  if can_see_client and job.client:
    job_info['client_name'] = job.client.name
    job_info['client_url'] = reverse('ci:view_client', args=[job.client.pk,])
  else:
    job_info['client_name'] = ''
    job_info['client_url'] = ''

  if job.last_modified < dt:
    # always return the basic info since we need to update the
    # "natural" time
    return JsonResponse({'job_info': job_info, 'results': [], 'last_request': this_request})

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
        'complete': result.status_slug(),
        }
    result_info.append(info)

  return JsonResponse({'job_info': job_info, 'results': result_info, 'last_request': this_request})

def job_results_html(request):
  """
  Used for testing the update with debug toolbar.
  """
  response = job_results(request)
  return render(request, 'ci/ajax_test.html', {'content': response.content})
