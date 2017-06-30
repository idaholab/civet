
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
from django.conf import settings
from mock import patch
from ci.github.api import GitHubAPI

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

    @patch.object(GitHubAPI, 'add_pr_label')
    @patch.object(GitHubAPI, 'remove_pr_label')
    def test_event_complete(self, mock_remove, mock_add):
        ev = utils.create_event(cause=models.Event.PUSH)
        request = self.factory.get('/')
        settings.FAILED_BUT_ALLOWED_LABEL_NAME = None

        # No label so we shouldn't do anything
        UpdateRemoteStatus.event_complete(request, ev)
        self.assertEqual(mock_add.call_count, 0)
        self.assertEqual(mock_remove.call_count, 0)

        settings.FAILED_BUT_ALLOWED_LABEL_NAME = 'foo'

        # event isn't a pull request, so we shouldn't do anything
        UpdateRemoteStatus.event_complete(request, ev)
        self.assertEqual(mock_add.call_count, 0)
        self.assertEqual(mock_remove.call_count, 0)

        ev.cause = models.Event.PULL_REQUEST
        ev.status = models.JobStatus.SUCCESS
        ev.pull_request = utils.create_pr()
        ev.save()
        # event is SUCCESS, so we shouldn't do anything
        UpdateRemoteStatus.event_complete(request, ev)
        self.assertEqual(mock_add.call_count, 0)
        self.assertEqual(mock_remove.call_count, 1)

        ev.status = models.JobStatus.FAILED
        ev.save()

        # Don't put anything if the event is FAILED
        UpdateRemoteStatus.event_complete(request, ev)
        self.assertEqual(mock_add.call_count, 0)
        self.assertEqual(mock_remove.call_count, 2)

        ev.status = models.JobStatus.FAILED_OK
        ev.save()

        # should try to add a label
        UpdateRemoteStatus.event_complete(request, ev)
        self.assertEqual(mock_add.call_count, 1)
        self.assertEqual(mock_remove.call_count, 2)
