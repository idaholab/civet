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
from django.test import override_settings
from django.tasks import default_task_backend
from mock import patch
from ci import tasks
from ci.github.api import GitHubAPI
from ci.client import UpdateRemoteStatus
from ci.tests import DBTester, utils


@override_settings(INSTALLED_GITSERVERS=[utils.github_config()])
class Tests(DBTester.DBTester):
    @patch.object(GitHubAPI, "update_status")
    def test_update_status(self, mock_status):
        ev = utils.create_event()
        tasks.update_status.enqueue(
            ev.pk,
            GitHubAPI.PENDING,
            "url",
            "Waiting",
            "context",
            GitHubAPI.STATUS_JOB_STARTED,
        )
        mock_status.assert_called_once_with(
            ev.base,
            ev.head,
            GitHubAPI.PENDING,
            "url",
            "Waiting",
            "context",
            GitHubAPI.STATUS_JOB_STARTED,
        )

    @patch.object(GitHubAPI, "pr_comment")
    def test_pr_comment(self, mock_comment):
        user = utils.create_user_with_token()
        tasks.pr_comment.enqueue(user.pk, "url", "msg")
        mock_comment.assert_called_once_with("url", "msg")

    @patch.object(GitHubAPI, "remove_pr_label")
    @patch.object(GitHubAPI, "add_pr_label")
    def test_pr_label(self, mock_add, mock_remove):
        user = utils.create_user_with_token()
        repo = utils.create_repo(user=user)
        tasks.add_pr_label.enqueue(user.pk, repo.pk, 1, "label")
        mock_add.assert_called_once_with(repo, 1, "label")
        tasks.remove_pr_label.enqueue(user.pk, repo.pk, 1, "label")
        mock_remove.assert_called_once_with(repo, 1, "label")

    @patch.object(GitHubAPI, "_remove_pr_todo_labels")
    def test_remove_pr_todo_labels(self, mock_remove):
        user = utils.create_user_with_token()
        tasks.remove_pr_todo_labels.enqueue(user.pk, "owner", "repo", 1, ["label"])
        mock_remove.assert_called_once_with("owner", "repo", 1, labels=["label"])

    @patch.object(UpdateRemoteStatus, "job_complete_remote")
    @patch.object(UpdateRemoteStatus, "event_complete")
    @patch.object(UpdateRemoteStatus, "job_complete_status")
    def test_complete(self, mock_job_status, mock_event, mock_job_remote):
        job = utils.create_job()
        tasks.job_complete_status.enqueue(job.pk, False)
        mock_job_status.assert_called_once_with(job, False)
        tasks.event_complete.enqueue(job.event.pk, True)
        mock_event.assert_called_once_with(job.event, True)
        tasks.job_complete_remote.enqueue(job.pk, True)
        mock_job_remote.assert_called_once_with(job, True)

    @override_settings(
        TASKS={"default": {"BACKEND": "django.tasks.backends.dummy.DummyBackend"}}
    )
    @patch.object(GitHubAPI, "pr_comment")
    @patch.object(GitHubAPI, "update_status")
    def test_deferred(self, mock_status, mock_comment):
        """
        The Git server isn't updated until the worker runs the tasks
        """
        self.create_default_recipes()
        ev = utils.create_event()
        job = utils.create_job(event=ev)
        job.init_pr_status()
        UpdateRemoteStatus.job_started(job)
        UpdateRemoteStatus.job_complete(job)
        self.assertEqual(mock_status.call_count, 0)
        self.assertEqual(mock_comment.call_count, 0)

        results = default_task_backend.results
        self.assertEqual(
            [r.task for r in results],
            [tasks.update_status, tasks.update_status, tasks.job_complete_remote],
        )
        # The statuses are captured when they are enqueued
        self.assertEqual(results[0].args[1:3], [GitHubAPI.PENDING, job.absolute_url()])
        self.assertEqual(results[1].args[1], GitHubAPI.RUNNING)

        for r in results:
            r.task.call(*r.args, **r.kwargs)
        # Pending, running, then the final status from completing the job
        self.assertEqual(
            [c.args[2] for c in mock_status.call_args_list],
            [GitHubAPI.PENDING, GitHubAPI.RUNNING, GitHubAPI.SUCCESS],
        )
