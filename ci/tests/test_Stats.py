
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

from __future__ import unicode_literals
import DBTester
from ci.tests import utils
from django.urls import reverse
from ci import Stats, TimeUtils
from ci import models
import datetime

class Tests(DBTester.DBTester):
    def test_set_passed(self):
        result = utils.create_step_result()
        result.save()
        context = {}
        start = (TimeUtils.get_local_time() - datetime.timedelta(days=1)).replace(hour=0, minute=0)
        bins = Stats.get_bins(start, datetime.timedelta(days=1))
        p = Stats.set_passed(start, "day", "Passed tests in last 6 months, by day", context, "month_chart", "%m/%d", bins)
        # no models.JobTestStatistics records
        for j in p[1:]:
            self.assertEqual(j[1], 0)
        self.assertIn("month_chart", context)

        context = {}
        models.JobTestStatistics.objects.create(job=result.job, passed=20, skipped=30, failed=40)
        p = Stats.set_passed(start, "day", "Passed tests in last 6 months, by day", context, "month_chart", "%m/%d", bins)
        self.assertNotEqual(context, {})
        self.assertEqual(len(p), 3)
        self.assertEqual(p[2][1], 20)
        self.assertIn("month_chart", context)

    def test_num_tests(self):
        result = utils.create_step_result()
        models.JobTestStatistics.objects.create(job=result.job, passed=20, skipped=30, failed=40)
        response = self.client.get(reverse('ci:num_tests'))
        self.assertEqual(response.status_code, 200)

    def test_repo_prs(self):
        repo0 = utils.create_repo(name="repo0")
        repo0.active = True
        repo0.save()
        utils.create_pr(title="pr0", number=1, repo=repo0)
        utils.create_pr(title="pr1", number=2, repo=repo0)
        repo1 = utils.create_repo(name="repo1")
        repo1.active = True
        repo1.save()
        utils.create_pr(repo=repo1)
        repo2 = utils.create_repo(name="repo2")
        repo2.active = True
        repo2.save()
        response = self.client.get(reverse('ci:num_prs'))
        self.assertEqual(response.status_code, 200)
