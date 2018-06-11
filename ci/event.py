
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
import logging
import re
from django.urls import reverse
from ci.client import UpdateRemoteStatus
logger = logging.getLogger('ci')

def cancel_event(ev, message, request=None, do_pr_status_update=True):
    """
    Cancels all jobs on an event
    Input:
      ev[models.Event]: Event to cancel
      message[str]: Message to put in the changelog
      request[django.http.HttpRequest]: If set, then try to update the remote status
    """
    logger.info('Canceling event {}: {}'.format(ev.pk, ev))
    cancelled_jobs = []
    for job in ev.jobs.all():
        if not job.complete:
            job.status = models.JobStatus.CANCELED
            job.complete = True
            job.save()
            logger.info('Canceling event {}: {} : job {}: {}'.format(ev.pk, ev, job.pk, job.str_with_client()))
            models.JobChangeLog.objects.create(job=job, message=message)
            cancelled_jobs.append(job)

    if ev.complete and ev.status == models.JobStatus.CANCELED and not cancelled_jobs:
        return
    ev.complete = True
    ev.save()
    ev.set_status(models.JobStatus.CANCELED)

    if request:
        for job in cancelled_jobs:
            job_url = request.build_absolute_uri(reverse('ci:view_job', args=[job.pk]))
            UpdateRemoteStatus.job_complete_pr_status(job_url, job, do_pr_status_update)
        UpdateRemoteStatus.event_complete(request, ev)

def get_active_labels(repo, changed_files):
    patterns = repo.get_repo_setting("recipe_label_activation", {})
    add_patterns = repo.get_repo_setting("recipe_label_activation_additive", {})
    if isinstance(add_patterns, list):
        logging.info("Using a list for recipe_label_activation_additive is no longer supported. Use a dictionary.")
        return [], True

    labels = {}
    matched_all = True

    for f in changed_files:
        for label, regex in patterns.items():
            if re.match(regex, f):
                count = labels.get(label, 0)
                labels[label] = count + 1
        for label, regex in add_patterns.items():
            if re.match(regex, f):
                count = labels.get(label, 0)
                labels[label] = count + 1
                matched_all = False

    if matched_all:
        for label in sorted(labels.keys()):
            # If a label doesn't match all the files then the matched labels
            # will be added to the recipes instead of just running only the matched label.
            if labels[label] != len(changed_files):
                matched_all = False
                break

    matched = sorted(list(labels.keys()))
    return matched, matched_all

def auto_cancel_event(ev, message):
    """
    Cancel all jobs on an event that have "auto_cancel_on_new_push" set to true.
    Input:
      ev: models.Event
    """
    logger.info('Auto canceling event {}: {}'.format(ev.pk, ev))
    for job in ev.jobs.all():
        if not job.complete and job.recipe.auto_cancel_on_push:
            job.status = models.JobStatus.CANCELED
            job.complete = True
            job.save()
            logger.info('Auto canceling event {}: {} : job {}: {}'.format(ev.pk, ev, job.pk, job.str_with_client()))
            models.JobChangeLog.objects.create(job=job, message=message)

    ev.save() # update the timestamp so the js updater works
    ev.set_complete_if_done()
