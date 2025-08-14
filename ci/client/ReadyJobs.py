# Copyright 2016-2025 Battelle Energy Alliance, LLC
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
from django.db.models import F, Q

def get_ready_jobs():
    jobs = (models.Job.objects
          .filter(complete=False,
                  active=True,
                  ready=True,
                  status=models.JobStatus.NOT_STARTED)
          .filter(Q(recipe__client_runner_user=None))
          .select_related('config',
                          'client',
                          'recipe__client_runner_user',
                          'recipe__build_user')
          .order_by(F('prioritized').desc(nulls_last=True), '-recipe__priority', 'created'))

    ready_jobs = []
    current_push_event_branches = set()
    for job in jobs.all():
      if job.event.cause == models.Event.PUSH and job.event.auto_cancel_event_except_current():
          current_push_event_branches.add(job.event.base.branch)
      else:
          ready_jobs.append(job)

    if current_push_event_branches:
      jobs = jobs.filter(event__base__branch__in=current_push_event_branches).order_by('created', '-recipe__priority')
      for job in jobs.all():
          ready_jobs.append(job)

    return ready_jobs
