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

    first_jobs = []
    later_jobs = []
    for job in jobs.all():
        # Delay push jobs that are not prioritized and have no set priority
        delay = job.event.cause == models.Event.PUSH and \
            job.prioritized is None and job.recipe.priority == 0

        if delay:
            later_jobs.append(job)
        else:
            first_jobs.append(job)

    return first_jobs + later_jobs
