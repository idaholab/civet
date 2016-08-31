
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
from django.utils import timezone
from ci import models
from ci import TimeUtils
import datetime
from optparse import make_option

class Command(BaseCommand):
    help = 'Show the number of tests run in the last 24 hours'
    option_list = BaseCommand.option_list + (
        make_option('--seconds-ago', default=None, dest='seconds', type='int',
            help='Specifies how many seconds in the past to start the search. Defaults to 1 day'),
        make_option('--csv', default=False, action='store_true', dest='csv',
          help='Write output in comma separated format: <start date>,<end date>,<num_test_steps>,<num_passed>,<num_skipped>,<num_failed>'),
        )

    def handle(self, *args, **options):
        seconds = options.get('seconds', None)
        csv = options.get('csv', False)
        if not seconds:
          seconds = 60*60*24
        dt = TimeUtils.get_datetime_since(seconds)
        job_stats = models.JobTestStatistics.objects.filter(job__last_modified__gte=dt).order_by('pk')
        passed = 0
        failed = 0
        skipped = 0
        for j in job_stats:
          passed += j.passed
          failed += j.failed
          skipped += j.skipped

        if csv:
          now = timezone.localtime(timezone.make_aware(datetime.datetime.utcnow()))
          print("{},{},{},{},{}".format(dt, now, passed, skipped, failed))
        else:
          print("Since {}".format(dt))
          print("Totals: {} passed, {} skipped, {} failed".format(passed, skipped, failed))
