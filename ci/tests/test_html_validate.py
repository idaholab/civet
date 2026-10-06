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
from django.test import TestCase, Client
from django.test.client import RequestFactory
from py_w3c.validators.html.validator import HTMLValidator
from django.urls import reverse
import json
from ci.tests import utils
from ci import models, Permissions
from mock import patch
import unittest, os


@unittest.skipIf(
    os.environ.get("VALIDATE_HTML") != "1", "run tests with VALIDATE_HTML=1"
)
class Tests(TestCase):
    def setUp(self):
        self.client = Client()
        self.factory = RequestFactory()
        for i in range(5):
            repo = utils.create_repo(name="repo%s" % i)
            repo.active = True
            repo.status = models.JobStatus.SUCCESS
            repo.save()
            for j in range(2):
                b = utils.create_branch(name="branch%s" % j, repo=repo)
                b.status = models.JobStatus.SUCCESS
                b.save()
            for j in range(3):
                b = repo.branches.first()
                pr = utils.create_pr(title="pr%s" % j, number=j + 1, repo=repo)
                pr.closed = False
                pr.status = models.JobStatus.SUCCESS
                pr.save()
                ev = utils.create_event(
                    user=repo.user, branch1=b, branch2=b, commit1="%s" % j
                )
                ev.pull_request = pr
                ev.save()
                for k in range(3):
                    r = utils.create_recipe(
                        name="%s%s" % (repo.name, k), repo=repo, branch=b
                    )
                    r.private = False
                    r.save()
                    job = utils.create_job(recipe=r, event=ev)
                    job.status = models.JobStatus.SUCCESS
                    job.client = utils.create_client(
                        name="client%s/%s" % (repo.name, k)
                    )
                    job.save()
                    utils.create_step_result(job=job)

    def check_url(self, url):
        response = self.client.get(url)
        vld = HTMLValidator()
        vld.validate_fragment(response.content)
        if vld.errors or vld.warnings:
            print(response.content)
        if vld.errors:
            print("ERRORS: %s" % json.dumps(vld.errors, indent=4))
        if vld.warnings:
            print("WARNINGS: %s" % json.dumps(vld.warnings, indent=4))
        self.assertEqual(vld.errors, [])
        self.assertEqual(vld.warnings, [])

    def test_main(self):
        self.check_url(reverse("ci:main"))

    def test_view_branch(self):
        self.check_url(
            reverse("ci:view_branch", args=[models.Branch.objects.first().pk])
        )

    def test_view_repo(self):
        self.check_url(
            reverse("ci:view_repo", args=[models.Repository.objects.first().pk])
        )

    def test_view_event(self):
        self.check_url(reverse("ci:view_event", args=[models.Event.objects.first().pk]))

    def test_view_pr(self):
        self.check_url(
            reverse("ci:view_pr", args=[models.PullRequest.objects.latest().pk])
        )

    def test_view_job(self):
        self.check_url(reverse("ci:view_job", args=[models.Job.objects.first().pk]))

    def test_view_client(self):
        self.check_url(
            reverse("ci:view_client", args=[models.Client.objects.first().pk])
        )

    def test_view_profile(self):
        self.check_url(
            reverse(
                "ci:view_profile", args=[models.Recipe.objects.first().build_user.pk]
            )
        )

    def test_user_repo_settings(self):
        user = utils.get_test_user()
        utils.simulate_login(self.client.session, user)
        self.check_url(reverse("ci:user_repo_settings"))

    def test_event_list(self):
        self.check_url(reverse("ci:event_list"))

    def test_pullrequest_list(self):
        self.check_url(reverse("ci:pullrequest_list"))

    def test_branch_list(self):
        self.check_url(reverse("ci:branch_list"))

    def test_client_list(self):
        self.check_url(reverse("ci:client_list"))

    def disable_client(self):
        """
        Disables a client that is still running a job.
        """
        job = models.Job.objects.first()
        job.status = models.JobStatus.RUNNING
        job.complete = False
        job.save()
        client = job.client
        client.status = models.Client.RUNNING
        client.disabled = True
        client.disabled_by = "admin"
        client.disabled_time = client.last_seen
        client.save()
        return client

    @patch.object(Permissions, "can_manage_clients", return_value=True)
    @patch.object(Permissions, "is_allowed_to_see_clients", return_value=True)
    def test_client_list_disabled(self, mock_allowed, mock_manage):
        self.disable_client()
        models.Client.objects.update(status=models.Client.RUNNING)
        self.check_url(reverse("ci:client_list"))

    @patch.object(Permissions, "can_manage_clients", return_value=True)
    @patch.object(Permissions, "is_allowed_to_see_clients", return_value=True)
    def test_view_client_disabled(self, mock_allowed, mock_manage):
        client = self.disable_client()
        self.check_url(reverse("ci:view_client", args=[client.pk]))
        # And the controls for an enabled client
        client = models.Client.objects.filter(disabled=False).first()
        self.check_url(reverse("ci:view_client", args=[client.pk]))

    def test_scheduled(self):
        self.check_url(reverse("ci:scheduled"))
