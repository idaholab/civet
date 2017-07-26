
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

    @patch.object(GitHubAPI, 'update_pr_status')
    def test_step_start_pr_status(self, mock_update):
        user = utils.get_test_user()
        job = utils.create_job(user=user)
        job.status = models.JobStatus.CANCELED
        job.save()
        results = utils.create_step_result(job=job)
        results.exit_status = 1
        results.save()
        request = self.factory.get('/')

        job.event.cause = models.Event.PUSH
        job.event.save()
        # Wrong cause
        UpdateRemoteStatus.step_start_pr_status(request, results, job)
        self.assertEqual(mock_update.call_count, 0)

        job.event.cause = models.Event.PULL_REQUEST
        job.event.save()
        # this would normally just update the remote status
        # not something we can check.
        # So just make sure that it doesn't throw
        UpdateRemoteStatus.step_start_pr_status(request, results, job)
        self.assertEqual(mock_update.call_count, 1)

    @patch.object(GitHubAPI, 'pr_comment')
    def test_add_comment(self, mock_comment):
        j = utils.create_job()
        j.event.cause = models.Event.PUSH
        j.event.save()
        request = self.factory.get('/')
        utils.simulate_login(self.client.session, j.event.build_user)
        auth = j.event.build_user.server.auth().start_session_for_user(j.event.build_user)

        # wrong cause
        UpdateRemoteStatus.add_comment(request, auth, j.event.build_user, j)
        self.assertEqual(mock_comment.call_count, 0)

        j.event.cause = models.Event.PULL_REQUEST
        j.event.save()

        # no comments_url
        UpdateRemoteStatus.add_comment(request, auth, j.event.build_user, j)
        self.assertEqual(mock_comment.call_count, 0)

        j.event.comments_url = 'url'
        j.event.save()

        settings.GITHUB_POST_JOB_STATUS = False
        # not posting job status
        UpdateRemoteStatus.add_comment(request, auth, j.event.build_user, j)
        self.assertEqual(mock_comment.call_count, 0)

        settings.GITHUB_POST_JOB_STATUS = True
        # OK
        UpdateRemoteStatus.add_comment(request, auth, j.event.build_user, j)
        self.assertEqual(mock_comment.call_count, 1)

    @patch.object(GitHubAPI, 'pr_comment')
    def test_create_event_summary(self, mock_comment):
        ev = utils.create_event()
        ev.comments_url = 'url'
        ev.save()
        j0 = utils.create_job(event=ev)
        config = utils.create_build_config("config1")
        j0.recipe.build_configs.add(config)
        utils.create_job(event=ev, recipe=j0.recipe, config=config)
        r1 = utils.create_recipe(name="r1")
        j1 = utils.create_job(recipe=r1, event=ev)
        j0.recipe.depends_on.add(r1)
        request = self.factory.get('/')
        settings.GITHUB_POST_EVENT_SUMMARY = False

        # Not posting the summary so we should do anything
        UpdateRemoteStatus.create_event_summary(request, ev)
        self.assertEqual(mock_comment.call_count, 0)

        settings.GITHUB_POST_EVENT_SUMMARY = True
        UpdateRemoteStatus.create_event_summary(request, ev)
        self.assertEqual(mock_comment.call_count, 1)

        j1.status = models.JobStatus.FAILED
        j1.complete = True
        j1.invalidated = True
        j1.save()
        utils.create_step_result(job=j1, status=models.JobStatus.FAILED)
        self.assertEqual(len(ev.get_unrunnable_jobs()), 2)
        UpdateRemoteStatus.create_event_summary(request, ev)
        self.assertEqual(mock_comment.call_count, 2)

    @patch.object(GitHubAPI, 'add_pr_label')
    @patch.object(GitHubAPI, 'remove_pr_label')
    def test_event_complete(self, mock_remove, mock_add):
        ev = utils.create_event(cause=models.Event.PUSH)
        ev.comments_url = 'url'
        ev.save()
        request = self.factory.get('/')
        settings.FAILED_BUT_ALLOWED_LABEL_NAME = None
        settings.GITHUB_POST_EVENT_SUMMARY = False

        # event isn't a pull request, so we shouldn't do anything
        UpdateRemoteStatus.event_complete(request, ev)
        self.assertEqual(mock_add.call_count, 0)
        self.assertEqual(mock_remove.call_count, 0)

        ev.cause = models.Event.PULL_REQUEST
        ev.status = models.JobStatus.SUCCESS
        ev.pull_request = utils.create_pr()
        ev.save()

        # Not complete, shouldn't do anything
        UpdateRemoteStatus.event_complete(request, ev)
        self.assertEqual(mock_add.call_count, 0)
        self.assertEqual(mock_remove.call_count, 0)

        ev.complete = True
        ev.save()

        # No label so we shouldn't do anything
        UpdateRemoteStatus.event_complete(request, ev)
        self.assertEqual(mock_add.call_count, 0)
        self.assertEqual(mock_remove.call_count, 0)

        settings.FAILED_BUT_ALLOWED_LABEL_NAME = 'foo'
        settings.GITHUB_POST_EVENT_SUMMARY = True

        # event is SUCCESS, so we shouldn't add a label but
        # we will try to remove an existing label
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
