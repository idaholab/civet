from ci import TimeUtils, models
from django.core.urlresolvers import reverse
from django.utils.html import format_html

def get_default_events_query(event_q=None):
  """
  Default events query that preloads all that will be needed in events_info()
  Input:
    event_q: An existing models.Event query
  Return:
    a query on models.Event
  """
  if event_q == None:
    event_q = models.Event.objects
  return event_q.order_by('-created').select_related(
      'base__branch__repository__user__server', 'head__branch__repository__user__server', 'pull_request').prefetch_related('jobs', 'jobs__recipe', 'jobs__recipe__depends_on')

def all_events_info(limit=30, last_modified=None):
  """
  Get the default events info list.
  Input:
    limit: int: Maximum number of results to return
    last_modified: DateTime: events with last_modified before this time are ignored.
  Return:
    list of event info dicts as returned by events_info()
  """
  event_q = get_default_events_query()[:limit]
  return events_info(event_q, last_modified)

def events_with_head(event_q=None):
  """
  In some cases we want the head commit information as well.
  Input:
    event_q: An existing query on model.Event
  Return:
    query on models.Event
  """
  if event_q == None:
    event_q = models.Event.objects
  return get_default_events_query(event_q).select_related('head__branch__repository__user')

def events_filter_by_repo(pks, limit=30, last_modified=None):
  event_q = get_default_events_query()
  event_q = event_q.filter(base__branch__repository__pk__in=pks)[:limit]
  return events_info(event_q, last_modified)

def events_info(events, last_modified=None, events_url=False):
  """
  Creates the information required for displaying events.
  Input:
    events: An iterable of models.Event. Usually a query or just a list.
    last_modified: DateTime: If model.Event.last_modified is before this it won't be included
  Return:
    list of event info dicts
  """
  event_info = []
  for ev in events:
    if last_modified and ev.last_modified <= last_modified:
      continue

    repo_url = reverse("ci:view_repo", args=[ev.base.branch.repository.pk])
    event_url = reverse("ci:view_event", args=[ev.pk])
    repo_link = '<a href="%s">%s</a>' % (repo_url, format_html(ev.base.branch.repository.name))
    pr_url = ''

    if ev.pull_request:
      pr_url = reverse("ci:view_pr", args=[ev.pull_request.pk])
      icon_link = '<a href="%s"><i class="%s"></i></a>' % (ev.pull_request.url, ev.base.server().icon_class())
      if events_url:
        event_desc = '%s %s <a href="%s">%s</a>' % (icon_link, repo_link, event_url, ev.pull_request)
      else:
        event_desc = '%s %s <a href="%s">%s</a>' % (icon_link, repo_link, pr_url, ev.pull_request)
    else:
      event_desc = '%s <a href="%s">%s' % (repo_link, event_url, ev.base.branch.name)
      if ev.description:
        event_desc += ': %s' % format_html(ev.description)
      event_desc += '</a>'

    info = { 'id': ev.pk,
        'status': ev.status_slug(),
        'last_modified': TimeUtils.human_time_str(ev.last_modified),
        'last_modified_date': TimeUtils.std_time_str(ev.last_modified),
        'created_date': TimeUtils.std_time_str(ev.created),
        'created': TimeUtils.human_time_str(ev.created),
        'sort_time': TimeUtils.sortable_time_str(ev.created),
        'repo_url': repo_url,
        'event_url': event_url,
        'base_name': format_html(str(ev.base)),
        'base_commit': ev.base.sha,
        'base_branch_id': ev.base.branch.pk,
        'base_branch_name': format_html(ev.base.branch.name),
        'base_repository_id': ev.base.branch.repository.pk,
        'base_repository_name': format_html(ev.base.branch.repository.name),
        'base_owner_name': format_html(ev.base.branch.repository.user.name),
        'base_owner_id': ev.base.branch.repository.user.pk,
        'description': format_html(event_desc),
        "head_owner": ev.head.branch.repository.user.name,
        "head_repository": ev.head.branch.repository.name,
        "head_branch": ev.head.branch.name,
        "head_commit": ev.head.sha,
        'head_name': format_html(str(ev.head)),
        'server_icon_class': ev.base.server().icon_class(),
        'pr_id': 0,
        'pr_title': "",
        'pr_status': "",
        'pr_number': 0,
        'pr_url': "",
        'git_pr_url': "",
        'pr_username': "",
        'pr_name': "",
        }
    if ev.pull_request:
      info["pr_id"] = ev.pull_request.pk
      info["pr_title"] = ev.pull_request.title
      info["pr_status"] = ev.pull_request.status_slug()
      info["pr_number"] = ev.pull_request.number
      info["git_pr_url"] = ev.pull_request.url
      info["pr_url"] = pr_url
      info["pr_username"] = ev.pull_request.username
      info["pr_name"] = format_html(str(ev.pull_request))

    job_info = []
    for job_group in ev.get_sorted_jobs():
      job_group_info = []
      for job in job_group:
        if int(job.seconds.total_seconds()) == 0:
          job_seconds = ""
        else:
          job_seconds = str(job.seconds)

        jinfo = { 'id': job.pk,
            'status': job.status_slug(),
            'url': reverse("ci:view_job", args=[job.pk]),
            'seconds': job_seconds,
            'recipe_name': format_html(job.recipe.display_name),
            'invalidated': job.invalidated,
            'complete': job.complete,
            'ready': job.ready,
            'active': job.active,
            'created_date': TimeUtils.std_time_str(job.created),
            'created': TimeUtils.human_time_str(job.created),
            'last_modified': TimeUtils.std_time_str(job.last_modified),
            'failed_step': job.failed_step,
            }
        job_desc = '<a href="%s">%s</a>' % (jinfo['url'], jinfo['recipe_name'])
        if job_seconds:
          job_desc += '<br />%s' % jinfo['seconds']
        if job.failed_step:
          job_desc += '<br />%s' % jinfo['failed_step']
        if job.invalidated:
          job_desc += '<br />(Invalidated)'
        jinfo["description"] = job_desc
        job_group_info.append(jinfo)
      job_info.append(job_group_info)
    info['job_groups'] = job_info

    event_info.append(info)

  return event_info
