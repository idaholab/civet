
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
from django.test import override_settings
from ci.client.tests import ClientTester
from ci import models
from ci.tests import utils
from ci.client import UpdateRemoteStatus
from mock import patch
from requests_oauthlib import OAuth2Session

@override_settings(INSTALLED_GITSERVERS=[utils.github_config()])
class Tests(ClientTester.ClientTester):

    @patch.object(OAuth2Session, 'post')
    def test_step_start_pr_status(self, mock_post):
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

        with self.settings(INSTALLED_GITSERVERS=[utils.github_config(remote_update=True)]):
            # Wrong cause
            UpdateRemoteStatus.step_start_pr_status(request, results, job)
            self.assertEqual(mock_post.call_count, 0)

            job.event.cause = models.Event.PULL_REQUEST
            job.event.save()

            # OK
            UpdateRemoteStatus.step_start_pr_status(request, results, job)
            self.assertEqual(mock_post.call_count, 1)

    @patch.object(OAuth2Session, 'post')
    def test_add_comment(self, mock_post):
        j = utils.create_job()
        j.event.cause = models.Event.PUSH
        j.event.save()
        job_url = "some url"
        api = j.event.build_user.api()

        # wrong cause
        UpdateRemoteStatus.add_comment(job_url, api, j.event.build_user, j)
        self.assertEqual(mock_post.call_count, 0)

        j.event.cause = models.Event.PULL_REQUEST
        j.event.save()

        # no comments_url
        UpdateRemoteStatus.add_comment(job_url, api, j.event.build_user, j)
        self.assertEqual(mock_post.call_count, 0)

        j.event.comments_url = 'url'
        j.event.save()

        with self.settings(INSTALLED_GITSERVERS=[utils.github_config(post_job_status=False, remote_update=True)]):
            # not posting job status
            UpdateRemoteStatus.add_comment(job_url, api, j.event.build_user, j)
            self.assertEqual(mock_post.call_count, 0)
            self.assertEqual(api._errors, [])

        with self.settings(INSTALLED_GITSERVERS=[utils.github_config(post_job_status=True, remote_update=True)]):
            # OK
            api = j.event.build_user.api()
            UpdateRemoteStatus.add_comment(job_url, api, j.event.build_user, j)
            self.assertEqual(mock_post.call_count, 1)

    @patch.object(OAuth2Session, 'post')
    @patch.object(OAuth2Session, 'get')
    def test_create_event_summary(self, mock_get, mock_post):
        mock_get.return_value = utils.Response()
        mock_post.return_value = utils.Response()
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

        with self.settings(INSTALLED_GITSERVERS=[utils.github_config(post_event_summary=False, remote_update=True)]):
            # Not posting the summary so we should do anything
            UpdateRemoteStatus.create_event_summary(request, ev)
            self.assertEqual(mock_post.call_count, 0)
            self.assertEqual(mock_get.call_count, 0)

        with self.settings(INSTALLED_GITSERVERS=[utils.github_config(post_event_summary=True, remote_update=True)]):
            UpdateRemoteStatus.create_event_summary(request, ev)
            self.assertEqual(mock_post.call_count, 1) # 1 for adding comment
            self.assertEqual(mock_get.call_count, 1) # 1 for getting current comments

            j1.status = models.JobStatus.FAILED
            j1.complete = True
            j1.invalidated = True
            j1.save()
            utils.create_step_result(job=j1, status=models.JobStatus.FAILED)
            self.assertEqual(len(ev.get_unrunnable_jobs()), 2)
            UpdateRemoteStatus.create_event_summary(request, ev)
            self.assertEqual(mock_post.call_count, 2)
            self.assertEqual(mock_get.call_count, 2)

    @patch.object(OAuth2Session, 'post')
    @patch.object(OAuth2Session, 'get')
    @patch.object(OAuth2Session, 'delete')
    def test_event_complete(self, mock_del, mock_get, mock_post):
        ev = utils.create_event(cause=models.Event.PUSH)
        ev.comments_url = 'url'
        ev.save()
        request = self.factory.get('/')

        git_config = utils.github_config(post_event_summary=False, failed_but_allowed_label_name=None, remote_update=True)
        with self.settings(INSTALLED_GITSERVERS=[git_config]):
            # event isn't a pull request, so we shouldn't do anything
            UpdateRemoteStatus.event_complete(request, ev)
            self.assertEqual(mock_get.call_count, 0)
            self.assertEqual(mock_post.call_count, 0)
            self.assertEqual(mock_del.call_count, 0)

            ev.cause = models.Event.PULL_REQUEST
            ev.status = models.JobStatus.SUCCESS
            ev.pull_request = utils.create_pr()
            ev.save()

            # Not complete, shouldn't do anything
            UpdateRemoteStatus.event_complete(request, ev)
            self.assertEqual(mock_get.call_count, 0)
            self.assertEqual(mock_post.call_count, 0)
            self.assertEqual(mock_del.call_count, 0)

            ev.complete = True
            ev.save()

            # No label so we shouldn't do anything
            UpdateRemoteStatus.event_complete(request, ev)
            self.assertEqual(mock_get.call_count, 0)
            self.assertEqual(mock_post.call_count, 0)
            self.assertEqual(mock_del.call_count, 0)

        git_config = utils.github_config(post_event_summary=False, failed_but_allowed_label_name='foo', remote_update=True)
        with self.settings(INSTALLED_GITSERVERS=[git_config]):
            # event is SUCCESS, so we shouldn't add a label but
            # we will try to remove an existing label
            UpdateRemoteStatus.event_complete(request, ev)
            self.assertEqual(mock_get.call_count, 0)
            self.assertEqual(mock_post.call_count, 0)
            self.assertEqual(mock_del.call_count, 1) # removing the label

            ev.status = models.JobStatus.FAILED
            ev.save()

            # Don't put anything if the event is FAILED
            UpdateRemoteStatus.event_complete(request, ev)
            self.assertEqual(mock_get.call_count, 0)
            self.assertEqual(mock_post.call_count, 0)
            self.assertEqual(mock_del.call_count, 2)

            ev.status = models.JobStatus.FAILED_OK
            ev.save()

            # should try to add a label
            UpdateRemoteStatus.event_complete(request, ev)
            self.assertEqual(mock_get.call_count, 0)
            self.assertEqual(mock_post.call_count, 1) # add the label
            self.assertEqual(mock_del.call_count, 2)

    @patch.object(OAuth2Session, 'patch')
    @patch.object(OAuth2Session, 'post')
    @patch.object(OAuth2Session, 'get')
    def test_create_issue_on_fail(self, mock_get, mock_post, mock_patch):
        j = utils.create_job()
        get_data = [{"title": "foo", "number": 1}]
        mock_get.return_value = utils.Response(get_data)
        mock_post.return_value = utils.Response({"html_url": "<html_url>"})
        mock_patch.return_value = utils.Response({"html_url": "<html_url>"})
        ju = "<some url>"

        git_config = utils.github_config(remote_update=True)
        with self.settings(INSTALLED_GITSERVERS=[git_config]):
            j.status = models.JobStatus.SUCCESS
            j.save()
            j.event.cause = models.Event.PULL_REQUEST
            j.event.save()

            # Don't do anything on a PR
            UpdateRemoteStatus.create_issue_on_fail(ju, j)
            self.assertEqual(mock_get.call_count, 0)
            self.assertEqual(mock_post.call_count, 0)
            self.assertEqual(mock_patch.call_count, 0)

            j.event.cause = models.Event.PUSH
            j.event.save()
            # Don't do anything unless it is a failure
            UpdateRemoteStatus.create_issue_on_fail(ju, j)
            self.assertEqual(mock_get.call_count, 0)
            self.assertEqual(mock_post.call_count, 0)
            self.assertEqual(mock_patch.call_count, 0)

            j.status = models.JobStatus.FAILED
            j.save()
            # Don't do anything unless the recipe wants to create an issue
            UpdateRemoteStatus.create_issue_on_fail(ju, j)
            self.assertEqual(mock_get.call_count, 0)
            self.assertEqual(mock_post.call_count, 0)
            self.assertEqual(mock_patch.call_count, 0)

            j.recipe.create_issue_on_fail = True
            j.recipe.save()
            # Should create new issue
            UpdateRemoteStatus.create_issue_on_fail(ju, j)
            self.assertEqual(mock_get.call_count, 1)
            self.assertEqual(mock_post.call_count, 1)
            self.assertEqual(mock_patch.call_count, 0)

    def test_start_canceled_on_fail(self):
        user = utils.get_test_user()
        r0 = utils.create_recipe(name='recipe0', user=user)
        r1 = utils.create_recipe(name='recipe1', user=user)
        r2 = utils.create_recipe(name='recipe2', user=user)
        e0 = utils.create_event(user=user, cause=models.Event.PUSH)
        j0 = utils.create_job(recipe=r0, event=e0, user=user)
        j0.status = models.JobStatus.SUCCESS
        j0.complete = True
        j0.save()
        j1 = utils.create_job(recipe=r1, event=e0, user=user)
        j1.status = models.JobStatus.CANCELED
        j1.complete = True
        j1.save()
        j2 = utils.create_job(recipe=r2, event=e0, user=user)
        j2.status = models.JobStatus.RUNNING
        j2.ready = True
        j2.save()
        e1 = utils.create_event(user=user, cause=models.Event.PUSH, commit1='12345')
        j3 = utils.create_job(recipe=r0, event=e1, user=user)
        j3.status = models.JobStatus.SUCCESS
        j3.complete = True
        j3.save()
        j4 = utils.create_job(recipe=r1, event=e1, user=user)
        j4.status = models.JobStatus.CANCELED
        j4.complete = True
        j4.save()
        j5 = utils.create_job(recipe=r2, event=e1, user=user)
        j5.status = models.JobStatus.RUNNING
        j5.complete = True
        j5.save()

        e2 = utils.create_event(user=user, cause=models.Event.PUSH, commit1='123456')
        j6 = utils.create_job(recipe=r0, event=e2, user=user)
        j6.status = models.JobStatus.SUCCESS
        j6.complete = True
        j6.save()
        j7 = utils.create_job(recipe=r1, event=e2, user=user)
        j7.status = models.JobStatus.FAILED
        j7.complete = True
        j7.save()
        j8 = utils.create_job(recipe=r2, event=e2, user=user)
        j8.status = models.JobStatus.FAILED_OK
        j8.complete = True
        j8.save()

        # If the job isn't a fail then it shouldn't do anything
        self.set_counts()
        UpdateRemoteStatus.start_canceled_on_fail(j6)
        self.compare_counts()

        # Normal behavior, a job fails and doesn't do anything to the previous event
        self.set_counts()
        UpdateRemoteStatus.start_canceled_on_fail(j7)
        self.compare_counts()

        repo_name = "%s/%s" % (e0.base.branch.repository.user.name, e0.base.branch.repository.name)
        branch_name = e0.base.branch.name
        branch_settings = {"auto_cancel_push_events_except_current": True, "auto_uncancel_previous_event": True}
        repo_settings={repo_name: {"branch_settings": {branch_name: branch_settings}}}
        with self.settings(INSTALLED_GITSERVERS=[utils.github_config(repo_settings=repo_settings)]):
            # If the job isn't a fail then it shouldn't do anything
            self.set_counts()
            UpdateRemoteStatus.start_canceled_on_fail(j3)
            self.compare_counts()

            # A job fails and should go to the previous event and uncancel any jobs
            self.set_counts()
            UpdateRemoteStatus.start_canceled_on_fail(j7)
            self.compare_counts(ready=1, active_branches=1, canceled=-1, invalidated=1, num_changelog=1, num_jobs_completed=-1)
            j0.refresh_from_db()
            self.assertEqual(j0.status, models.JobStatus.SUCCESS)
            j1.refresh_from_db()
            self.assertEqual(j1.status, models.JobStatus.CANCELED)
            self.assertTrue(j1.complete)
            j2.refresh_from_db()
            self.assertEqual(j2.status, models.JobStatus.RUNNING)
            j3.refresh_from_db()
            self.assertEqual(j3.status, models.JobStatus.SUCCESS)
            j4.refresh_from_db()
            self.assertEqual(j4.status, models.JobStatus.NOT_STARTED)
            self.assertFalse(j4.complete)
            j5.refresh_from_db()
            self.assertEqual(j5.status, models.JobStatus.RUNNING)
