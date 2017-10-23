
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
from ci.client import UpdateRemoteStatus
logger = logging.getLogger('ci')

def cancel_event(ev, message, request=None):
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
            if request:
                UpdateRemoteStatus.job_complete_pr_status(request, job)

    ev.complete = True
    ev.save()
    ev.set_status(models.JobStatus.CANCELED, True)
    if request:
        UpdateRemoteStatus.event_complete(request, ev)


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
