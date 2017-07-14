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

from ci import models
from django.core.urlresolvers import reverse
import ProcessCommands

def add_comment(request, oauth_session, user, job):
    """
    Add a comment to the PR to indicate the status of the job.
    This typically only happens when the job is finished.
    """
    if job.event.cause != models.Event.PULL_REQUEST:
        return
    if not job.event.comments_url:
        return
    if not user.server.post_job_status():
        return

    abs_job_url = request.build_absolute_uri(reverse('ci:view_job', args=[job.pk]))
    comment = 'Testing {}\n\n[{}]({}) : **{}**\n'.format(job.event.head.short_sha(), job.unique_name(), abs_job_url, job.status_str())
    comment += '\nView the results [here]({}).\n'.format(abs_job_url)
    user.server.api().pr_comment(oauth_session, job.event.comments_url, comment)

def job_started(request, job):
    """
    Indicates that the job as started.
    This will update the CI status on the Git server.
    """
    if job.event.cause == models.Event.PULL_REQUEST:
        user = job.event.build_user
        oauth_session = user.server.auth().start_session_for_user(user)
        api = user.server.api()
        api.update_pr_status(
            oauth_session,
            job.event.base,
            job.event.head,
            api.PENDING,
            request.build_absolute_uri(reverse('ci:view_job', args=[job.pk])),
            'Starting',
            job.unique_name(),
            api.STATUS_JOB_STARTED,
            )

def step_start_pr_status(request, step_result, job):
    """
    This gets called when the client starts a step.
    Just tries to update the status on the server.
    """

    if job.event.cause != models.Event.PULL_REQUEST:
        return

    user = job.event.build_user
    server = user.server
    oauth_session = server.auth().start_session_for_user(user)
    api = server.api()
    status = api.RUNNING
    desc = '({}/{}) {}'.format(step_result.position+1, job.step_results.count(), step_result.name)
    job_stage = api.STATUS_CONTINUE_RUNNING
    if step_result.position == 0:
        job_stage = api.STATUS_START_RUNNING

    api.update_pr_status(
        oauth_session,
        job.event.base,
        job.event.head,
        status,
        request.build_absolute_uri(reverse('ci:view_job', args=[job.pk])),
        desc,
        job.unique_name(),
        job_stage,
        )

def job_complete_pr_status(request, job):
    """
    Indicates that the job has completed.
    This will update the CI status on the Git server and
    try to add a comment.
    """
    user = job.event.build_user
    oauth_session = user.server.auth().start_session_for_user(user)
    api = user.server.api()

    if job.event.cause == models.Event.PULL_REQUEST:
        status_dict = { models.JobStatus.FAILED_OK:(api.SUCCESS, "Failed but allowed"),
            models.JobStatus.CANCELED: (api.CANCELED, "Canceled"),
            models.JobStatus.FAILED: (api.FAILURE, "Failed"),
            }
        status, msg = status_dict.get(job.status, (api.SUCCESS, "Passed"))

        api.update_pr_status(
            oauth_session,
            job.event.base,
            job.event.head,
            status,
            request.build_absolute_uri(reverse('ci:view_job', args=[job.pk])),
            msg,
            job.unique_name(),
            api.STATUS_JOB_COMPLETE,
            )
        add_comment(request, oauth_session, user, job)

def job_wont_run(request, job):
    """
    Indicates that the job will not be run at all.
    This will update the CI status on the Git server.
    """
    user = job.event.build_user
    oauth_session = user.server.auth().start_session_for_user(user)
    api = user.server.api()
    if job.event.cause == models.Event.PULL_REQUEST:
        api.update_pr_status(
            oauth_session,
            job.event.base,
            job.event.head,
            api.CANCELED,
            request.build_absolute_uri(reverse('ci:view_job', args=[job.pk])),
            "Won't run due to failed dependencies",
            job.unique_name(),
            api.STATUS_JOB_COMPLETE,
            )

def create_event_summary(request, event):
    """
    Posts a comment on a PR with a summary of all the job statuses.
    """
    if event.cause != models.Event.PULL_REQUEST or not event.comments_url or not event.base.server().post_event_summary():
        return
    unrunnable = event.get_unrunnable_jobs()
    sorted_jobs = event.get_sorted_jobs()
    msg = "CIVET Testing summary for %s\n\n" % event.head.short_sha()
    msg_re = r"^%s" % msg
    for group in sorted_jobs:
        for j in group:
            # be careful to put two ending spaces on each line so we get proper line breaks
            abs_job_url = request.build_absolute_uri(reverse('ci:view_job', args=[j.pk]))
            if j.status == models.JobStatus.NOT_STARTED and j in unrunnable:
                msg += "[%s](%s) : Won't run due to failed dependencies  \n" % (j.unique_name(), abs_job_url)
            else:
                inv = ""
                if j.invalidated:
                    inv = " (Invalidated)"
                msg += "[%s](%s) : **%s**%s  \n" % (j.unique_name(), abs_job_url, j.status_str(), inv)

    session = event.build_user.start_session()
    ProcessCommands.edit_comment(session, event.base.server().api(), event.build_user, event.comments_url, msg, msg_re)

def event_complete(request, event):
    """
    The event is complete (all jobs have finished).
    Check to see if there are "Failed but allowed"
    jobs that wouldn't be obvious on the status.
    (ie GitHub would just show a green checkmark).
    If there are add an appropiate label.
    """
    if event.cause != models.Event.PULL_REQUEST:
        return

    create_event_summary(request, event)

    label = models.failed_but_allowed_label()
    if not label:
        return

    user = event.build_user
    api = user.server.api()
    if event.status == models.JobStatus.FAILED_OK:
        api.add_pr_label(user, event.base.repo(), event.pull_request.number, label)
    else:
        api.remove_pr_label(user, event.base.repo(), event.pull_request.number, label)
