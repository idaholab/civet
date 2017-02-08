
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

import models
import logging
import re
from django.conf import settings
logger = logging.getLogger('ci')

def job_status(job):
    """
    Figure out what the overall status of a job is.
    This is primarily used when the job is finished.
    While it is running we usually hard code the status.
    Input:
      job: models.Job
    Return:
      models.JobStatus of the job
    """
    status = set()
    for step_result in job.step_results.all():
        status.add(step_result.status)

    if models.JobStatus.RUNNING in status:
        return models.JobStatus.RUNNING
    if models.JobStatus.FAILED in status:
        return models.JobStatus.FAILED
    if models.JobStatus.CANCELED in status:
        return models.JobStatus.CANCELED
    if models.JobStatus.FAILED_OK in status:
        return models.JobStatus.FAILED_OK
    if models.JobStatus.SUCCESS in status:
        return models.JobStatus.SUCCESS
    return models.JobStatus.NOT_STARTED

def event_status(event):
    """
    Figure out what the overall status of an event is.
    Input:
      event: models.Event
    Return:
      a models.JobStatus of the event
    """
    status = set()
    for job in event.jobs.filter(active=True, ready=True).all():
        status.add(job.status)

    if models.JobStatus.RUNNING in status:
        return models.JobStatus.RUNNING
    if models.JobStatus.FAILED in status:
        return models.JobStatus.FAILED
    if models.JobStatus.FAILED_OK in status:
        return models.JobStatus.FAILED_OK
    if models.JobStatus.CANCELED in status:
        return models.JobStatus.CANCELED
    if models.JobStatus.SUCCESS in status:
        return models.JobStatus.SUCCESS
    return models.JobStatus.NOT_STARTED

def cancel_event(ev, message):
    """
    Cancels all jobs on an event
    Input:
      ev: models.Event
    """
    logger.info('Canceling event {}: {}'.format(ev.pk, ev))
    for job in ev.jobs.all():
        if not job.complete:
            job.status = models.JobStatus.CANCELED
            job.complete = True
            job.save()
            logger.info('Canceling event {}: {} : job {}: {}'.format(ev.pk, ev, job.pk, job))
            models.JobChangeLog.objects.create(job=job, message=message)

    ev.complete = True
    ev.status = models.JobStatus.CANCELED
    ev.save()

def make_jobs_ready(event):
    """
    Marks jobs attached to an event as ready to run.

    Jobs are checked to see if dependencies are met and
    if so, then they are marked as ready.
    Input:
      event: models.Event: The event to check jobs for
    """
    completed_jobs = event.jobs.filter(complete=True, active=True)

    if event.jobs.filter(active=True).count() == completed_jobs.count():
        event.complete = True
        event.save()
        logger.info('Event {}: {} complete'.format(event.pk, event))
        return

    job_depends = event.get_job_depends_on()
    for job, deps in job_depends.iteritems():
        if job.complete or job.ready or not job.active:
            continue
        ready = True
        for d in deps:
            if not d.complete or d.status not in [models.JobStatus.FAILED_OK, models.JobStatus.SUCCESS]:
                logger.info('job {}: {} does not have depends met: {}'.format(job.pk, job, d))
                ready = False
                break

        if ready:
            job.ready = ready
            job.save()
            logger.info('Job {}: {} : ready: {} : on {}'.format(job.pk, job, job.ready, job.recipe.repository))

def get_active_labels(changed_files):
    patterns = getattr(settings, "RECIPE_LABEL_ACTIVATION", {})
    labels = {}
    for label, regex in patterns.items():
        for f in changed_files:
            if re.match(regex, f):
                count = labels.get(label, 0)
                labels[label] = count + 1
    matched_all = True
    matched = []
    for label in sorted(labels.keys()):
        matched.append(label)
        if labels[label] != len(changed_files):
            matched_all = False
    return matched, matched_all
