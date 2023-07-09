
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
from ci import TimeUtils, models
from django.urls import reverse
from django.utils.html import format_html, mark_safe
from django.db.models import Prefetch
import copy
from django.utils.encoding import force_str

def get_default_events_query(event_q=None, filter_repo_ids=None):
    """
    Default events query that preloads all that will be needed in events_info()
    Input:
      event_q: An existing models.Event query
      filter_repo_ids: list: A list of repo IDs to filter, if any
    Return:
      a query on models.Event
    """
    if event_q == None:
        event_q = models.Event.objects

    jobs_q = models.Job.objects.select_related('config', 'recipe'
            ).prefetch_related('recipe__build_configs','recipe__depends_on',)
    event_q = event_q.order_by('-created').select_related(
        'base__branch__repository__user__server',
        'head__branch__repository__user__server',
        'pull_request')
    if filter_repo_ids is not None:
        event_q = event_q.filter(base__branch__repository__id__in=filter_repo_ids)
    return event_q.prefetch_related(Prefetch('jobs', queryset=jobs_q))

def all_events_info(limit=30, last_modified=None, filter_repo_ids=None):
    """
    Get the default events info list.
    Input:
      limit: int: Maximum number of results to return
      last_modified: DateTime: events with last_modified before this time are ignored.
      filter_repo_ids: list: A list of repo IDs to filter, if any
    Return:
      list of event info dicts as returned by multiline_events_info()
    """
    event_q = get_default_events_query(filter_repo_ids=filter_repo_ids)[:limit]
    return multiline_events_info(event_q, last_modified)

def get_single_event_for_open_prs(open_prs, last_modified=None, filter_repo_ids=None):
    """
    Get the latest event for a set of open prs
    Input:
        list[int]: A list of models.PullRequest.pk
        last_modified[Datetime]: Limit results to those modified after this date
        filter_repo_ids: list: A list of repo IDs to filter, if any
    Return:
        list[models.Event]: The latest event for each pull request
    """
    if not open_prs:
        return []
    prs = models.PullRequest.objects.filter(pk__in=open_prs)
    if filter_repo_ids is not None:
        prs = prs.filter(repository__id__in=filter_repo_ids)
    evs = []
    for pr in prs.all():
        ev = pr.events.order_by('-created').first()
        if not last_modified or ev.last_modified >= last_modified:
            evs.append(ev)
    return sorted(evs, key=lambda obj: obj.created)

def events_with_head(event_q=None, filter_repo_ids=None):
    """
    In some cases we want the head commit information as well.
    Input:
      event_q: An existing query on model.Event
      filter_repo_ids: list: A list of repo IDs to filter, if any
    Return:
      query on models.Event
    """
    if event_q == None:
        event_q = models.Event.objects
    event_q = get_default_events_query(event_q, filter_repo_ids=filter_repo_ids)
    return event_q.select_related('head__branch__repository__user')

def events_filter_by_repo(pks, limit=30, last_modified=None):
    event_q = get_default_events_query()
    event_q = event_q.filter(base__branch__repository__pk__in=pks)[:limit]
    return multiline_events_info(event_q, last_modified)

def clean_str_for_format(s):
    new_s = force_str(s).replace("{", "{{")
    new_s = new_s.replace("}", "}}")
    words = []
    # Really long words cause havoc on the table of events.
    # We could try to insert <wbr> so the browser breaks it
    # up but truncating is much simpler.
    for s in new_s.split():
        if len(s) > 20:
            s = "%s..." % s[:17]
        words.append(s)
    return " ".join(words)

def chunks(l, n):
    for i in range(0, len(l), n):
        yield l[i:i+n]

def multiline_events_info(events, last_modified=None, events_url=False, max_jobs_per_line=11):
    """
    Creates the information required for displaying events.
    This will ensure that each line is at most max_jobs_per_line
    Input:
      events: An iterable of models.Event. Usually a query or just a list.
      last_modified: DateTime: If model.Event.last_modified is before this it won't be included
      max_jobs_per_line: int: Number of jobs to break the line on
    Return:
      list of event info dicts
    """
    ev_info = events_info(events, last_modified, events_url)
    lines = []
    for ev in ev_info:
        new_ev = copy.deepcopy(ev)
        new_ev["job_groups"] = []
        # first flatten out the jobs
        flat_jobs = []
        for group_idx, group in enumerate(ev["job_groups"]):
            for job in group:
                flat_jobs.append(job)
            if group_idx != (len(ev["job_groups"])-1):
                flat_jobs.append({"id": 0})

        # now break it up into max_jobs_per_line
        multi = list(chunks(flat_jobs, max_jobs_per_line))
        line_count = 1000
        for idx, line in enumerate(multi):
            new_line = copy.deepcopy(ev)
            if idx != 0:
                new_line["description"] = ''
                new_line["id"] = "%s_%s" % (ev["id"], line_count-idx)
                new_line["sort_time"] = "{}{:04}".format(ev["sort_time"], line_count-idx)
                new_line["status"] = "ContinueLine"
            new_line["jobs"] = line
            new_line["job_groups"] = []
            lines.append(new_line)

    return lines

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
        repo_link = format_html('<a href="{}">{}</a>', repo_url, ev.base.branch.repository.name)
        pr_url = ''
        pr_desc = ''
        if ev.pull_request:
            pr_url = reverse("ci:view_pr", args=[ev.pull_request.pk])
            pr_desc = clean_str_for_format(str(ev.pull_request))
            icon_link = format_html('<a href="{}"><i class="{}"></i></a>', ev.pull_request.url, ev.base.server().icon_class())
            if events_url:
                event_desc = format_html('{} {} <a href="{}">{}</a>', icon_link, repo_link, event_url, pr_desc)
            else:
                event_desc = format_html('{} {} <a href="{}">{}</a>', icon_link, repo_link, pr_url, pr_desc)
        else:
            event_desc = format_html('{} <a href="{}">{}', repo_link, event_url, ev.base.branch.name)
            if ev.description:
                event_desc = format_html('{} : {}', mark_safe(event_desc), clean_str_for_format(ev.description))
            event_desc += '</a>'

        info = { 'id': ev.pk,
            'status': ev.status_slug(),
            'sort_time': TimeUtils.sortable_time_str(ev.created),
            'description': format_html(event_desc),
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
            info["pr_name"] = pr_desc

        job_info = []
        for job_group in ev.get_sorted_jobs():
            job_group_info = []
            for job in job_group:
                if int(job.seconds.total_seconds()) == 0:
                    job_seconds = ""
                else:
                    job_seconds = str(job.seconds)

                jurl = reverse("ci:view_job", args=[job.pk])

                jinfo = { 'id': job.pk,
                    'status': job.status_slug(),
                    }
                job_desc = format_html('<a href="{}">{}</a>', jurl, format_html(job.unique_name()))
                if job_seconds:
                    job_desc += format_html('<br />{}', job_seconds)
                if job.failed_step:
                    job_desc += format_html('<br />{}', job.failed_step)
                if job.running_step:
                    job_desc += format_html('<br />{}', job.running_step)
                if job.invalidated:
                    job_desc += '<br />(Invalidated)'
                jinfo["description"] = job_desc
                job_group_info.append(jinfo)
            job_info.append(job_group_info)
        info['job_groups'] = job_info

        event_info.append(info)

    return event_info
