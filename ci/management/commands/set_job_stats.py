
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

from django.core.management.base import BaseCommand
from ci.client import ParseOutput
from ci import models

class Command(BaseCommand):
    help = 'Set the test stats for all jobs'

    def handle(self, *args, **options):
        for j in models.Job.objects.iterator():
            ParseOutput.set_job_stats(j)
            j.refresh_from_db()
            if j.test_stats.exists():
                print("%s: %s" % (j, j.test_stats.first()))
