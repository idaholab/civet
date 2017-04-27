
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

import ClientTester
from ci import models
from ci.tests import utils
from ci.client import UpdateRemoteStatus

class Tests(ClientTester.ClientTester):
    def test_step_start_pr_status(self):
        user = utils.get_test_user()
        job = utils.create_job(user=user)
        job.status = models.JobStatus.CANCELED
        job.save()
        results = utils.create_step_result(job=job)
        results.exit_status = 1
        results.save()
        request = self.factory.get('/')
        # this would normally just update the remote status
        # not something we can check.
        # So just make sure that it doesn't throw
        UpdateRemoteStatus.step_start_pr_status(request, results, job)
