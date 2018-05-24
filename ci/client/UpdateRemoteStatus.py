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
from ci import models
from django.urls import reverse
from ci.client import ProcessCommands
from ci.client import ParseOutput
import logging
logger = logging.getLogger('ci')

def add_comment(abs_job_url, git_api, user, job):
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

    comment = 'Testing {}\n\n[{}]({}) : **{}**\n'.format(job.event.head.short_sha(),
            job.unique_name(),
            abs_job_url,
            job.status_str())
    comment += '\nView the results [here]({}).\n'.format(abs_job_url)
    git_api.pr_comment(job.event.comments_url, comment)

def job_started(request, job):
    """
    Indicates that the job as started.
    This will update the CI status on the Git server.
    """
    if job.event.cause == models.Event.PULL_REQUEST:
        git_api = job.event.build_user.api()
        git_api.update_pr_status(
            job.event.base,
            job.event.head,
            git_api.RUNNING, # Should have been set to PENDING when the PR event got processed
            request.build_absolute_uri(reverse('ci:view_job', args=[job.pk])),
            'Starting',
            job.unique_name(),
            git_api.STATUS_JOB_STARTED,
            )

def step_start_pr_status(request, step_result, job):
    """
    This gets called when the client starts a step.
    Just tries to update the status on the server.
    """

    if job.event.cause != models.Event.PULL_REQUEST:
        return

    git_api = job.event.build_user.api()
    status = git_api.RUNNING
    desc = '({}/{}) {}'.format(step_result.position+1, job.step_results.count(), step_result.name)
    job_stage = git_api.STATUS_CONTINUE_RUNNING
    if step_result.position == 0:
        job_stage = git_api.STATUS_START_RUNNING

    git_api.update_pr_status(
        job.event.base,
        job.event.head,
        status,
        request.build_absolute_uri(reverse('ci:view_job', args=[job.pk])),
        desc,
        job.unique_name(),
        job_stage,
        )

def job_complete_pr_status(job_url, job, do_status_update=True):
    """
    Indicates that the job has completed.
    This will update the CI status on the Git server and
    try to add a comment.
    """
    if job.event.cause == models.Event.PULL_REQUEST:
        git_api = job.event.build_user.api()
        if do_status_update:
            status_dict = { models.JobStatus.FAILED_OK:(git_api.SUCCESS, "Failed but allowed"),
                models.JobStatus.CANCELED: (git_api.CANCELED, "Canceled"),
                models.JobStatus.FAILED: (git_api.FAILURE, "Failed"),
                }
            status, msg = status_dict.get(job.status, (git_api.SUCCESS, "Passed"))

            git_api.update_pr_status(
                job.event.base,
                job.event.head,
                status,
                job_url,
                msg,
                job.unique_name(),
                git_api.STATUS_JOB_COMPLETE,
                )
        add_comment(job_url, git_api, job.event.build_user, job)

def create_issue_on_fail(job_url, job):
    """
    Creates or updates an issue on job failure.
    This doesn't happen on PRs.
    """
    if (job.event.cause == models.Event.PULL_REQUEST
            or job.status != models.JobStatus.FAILED
            or not job.recipe.create_issue_on_fail
            ):
        return

    git_api = job.event.build_user.api()

    commit = job.event.head
    comment = 'Testing {}\n\n[{}]({}) : **{}**\n'.format(commit.short_sha(),
            job.unique_name(),
            job_url,
            job.status_str())
    comment += '\nView the results [here]({}).\n'.format(job_url)

    title = "CIVET: '%s' failure" % job.unique_name()

    repo = commit.repo()
    git_api.create_or_update_issue(repo.user.name, repo.name, title, comment)

def check_automerge(event):
    """
    See if we should automerge a PR
    """
    repo = event.base.repo()
    if (event.cause != models.Event.PULL_REQUEST
            or event.status != models.JobStatus.SUCCESS
            or not repo.auto_merge_enabled()):
        return

    git_api = event.build_user.api()
    git_api.automerge(repo, event.pull_request.number)

def job_wont_run(job_url, job):
    """
    Indicates that the job will not be run at all.
    This will update the CI status on the Git server.
    """
    if job.event.cause == models.Event.PULL_REQUEST:
        git_api = job.event.build_user.api()
        git_api.update_pr_status(
            job.event.base,
            job.event.head,
            git_api.CANCELED,
            job_url,
            "Won't run due to failed dependencies",
            job.unique_name(),
            git_api.STATUS_JOB_COMPLETE,
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
                failed = ""
                if j.invalidated:
                    inv = " (Invalidated)"
                if j.failed():
                    result = j.failed_result()
                    if result:
                        failed = " : %s" % result.name
                msg += "[%s](%s) : **%s**%s%s  \n" % (j.unique_name(), abs_job_url, j.status_str(), failed, inv)

    git_api = event.build_user.api()
    ProcessCommands.edit_comment(git_api, event.build_user, event.comments_url, msg, msg_re)

def push_event_complete(request, event):
    if (event.cause != models.Event.PUSH
            or not event.complete
            or not event.auto_uncancel_previous_event()
            or event.status != models.JobStatus.FAILED):
        return
    uncancel_previous_event(event)

def pr_event_complete(request, event):
    """
    The event is complete (all jobs have finished).
    Check to see if there are "Failed but allowed"
    jobs that wouldn't be obvious on the status.
    (ie GitHub would just show a green checkmark).
    If there are add an appropiate label.
    """
    if event.cause != models.Event.PULL_REQUEST or not event.complete:
        return

    create_event_summary(request, event)

    check_automerge(event)

    label = event.base.repo().failed_but_allowed_label()
    if not label:
        return

    git_api = event.build_user.api()
    if event.status == models.JobStatus.FAILED_OK:
        git_api.add_pr_label(event.base.repo(), event.pull_request.number, label)
    else:
        git_api.remove_pr_label(event.base.repo(), event.pull_request.number, label)

def event_complete(request, event):
    if not event.complete:
        return
    if event.cause == models.Event.PULL_REQUEST:
        pr_event_complete(request, event)
    elif event.cause == models.Event.PUSH:
        push_event_complete(request, event)


def start_canceled_on_fail(job):
    """
    If we auto cancel this (failed) job and it is on a push event on a configured branch,
    then uncancel all the canceled jobs on the previous event.
    """
    if (job.event.cause != models.Event.PUSH
            or not job.event.auto_uncancel_previous_event()
            or job.status != models.JobStatus.FAILED):
        return
    job_url = reverse('ci:view_job', args=[job.pk])
    logger.info("%s push got failed job: %s" % (job.event, job))
    uncancel_previous_event(job.event, job_url)


def uncancel_previous_event(ev, job_url=None):
    ev_q = models.Event.objects.filter(cause=models.Event.PUSH,
            base__branch=ev.base.branch,
            created__lt=ev.created,
            ).order_by("-created")
    prev_ev = ev_q.first()
    if prev_ev:
        logger.info("%s: trying to uncancel" % prev_ev)
        ev_url = reverse('ci:view_event', args=[ev.pk])
        if job_url:
            msg = "Auto uncancelled due to failed <a href='%s'>job</a> on <a href='%s'>event</a>" % (job_url, ev_url)
        else:
            msg = "Auto uncancelled due to failed <a href='%s'>event</a>" % ev_url

        # The whole point of uncancelling a previous event is to find one
        # that isn't going to fail. So if the previous event is already failed,
        # go back further
        failed = False
        jobs_to_invalidate = []
        for j in prev_ev.jobs.order_by('-recipe__priority', 'created').all():
            if j.status == models.JobStatus.FAILED:
                failed = True
                break
            elif j.status == models.JobStatus.CANCELED:
                jobs_to_invalidate.append(j)

        if failed:
            logger.info("%s: Not going to uncancel due to existing failed job(s)" % prev_ev)
            uncancel_previous_event(prev_ev, job_url)
        elif jobs_to_invalidate:
            for j in jobs_to_invalidate:
                j.set_invalidated(msg)
            prev_ev.complete = False
            prev_ev.save()
            prev_ev.make_jobs_ready()

def job_complete(request, job):
    """
    Should be called whenever a job is completed.
    This will update the Git server status and make
    any additional jobs ready.
    """
    job_url = request.build_absolute_uri(reverse('ci:view_job', args=[job.pk]))
    job_complete_pr_status(job_url, job)
    create_issue_on_fail(job_url, job)
    start_canceled_on_fail(job)

    ParseOutput.set_job_info(job)
    ProcessCommands.process_commands(job_url, job)

    all_done = job.event.set_complete_if_done()

    if all_done:
        event_complete(request, job.event)
        unrunnable = job.event.get_unrunnable_jobs()
        for norun in unrunnable:
            logger.info("Job %s: %s will not run due to failed dependencies" % (norun.pk, norun))
            job_wont_run(job_url, norun)
    return all_done
