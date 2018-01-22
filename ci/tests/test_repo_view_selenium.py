
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

import SeleniumTester
from django.test import override_settings
import utils
from ci import models
from django.urls import reverse

@override_settings(INSTALLED_GITSERVERS=[utils.github_config()])
class Tests(SeleniumTester.SeleniumTester):
    @SeleniumTester.test_drivers()
    def test_basic(self):
        repo, branch = self.create_repo_with_prs()
        url = reverse('ci:view_repo', args=[repo.pk])
        self.get(url)
        self.check_repos()
        self.check_events()

    @SeleniumTester.test_drivers()
    def test_repo_update_all(self):
        repo, branch = self.create_repo_with_prs()
        url = reverse('ci:view_repo', args=[repo.pk])
        self.get(url)
        self.check_repos()
        self.check_events()
        self.wait_for_js()

        branch.status = models.JobStatus.SUCCESS
        branch.save()
        for pr in repo.pull_requests.all():
            pr.status = models.JobStatus.SUCCESS
            pr.title = "New title"
            pr.username = "foobar"
            pr.save()
        self.wait_for_js()
        self.check_js_error()
        self.check_repos()
        self.check_events()

    @SeleniumTester.test_drivers()
    def test_repo_update_branch(self):
        repo, branch = self.create_repo_with_prs()
        url = reverse('ci:view_repo', args=[repo.pk])
        self.get(url)
        self.check_repos()
        self.check_events()
        # need to sleep so that last_modified will trigger
        self.wait_for_js()

        branch.status = models.JobStatus.SUCCESS
        branch.save()
        self.wait_for_js()
        self.check_js_error()
        self.check_repos()
        self.check_events()

    @SeleniumTester.test_drivers()
    def test_repo_update_pr(self):
        repo, branch = self.create_repo_with_prs()
        url = reverse('ci:view_repo', args=[repo.pk])
        self.get(url)
        self.check_repos()
        self.check_events()
        self.wait_for_js()

        pr = repo.pull_requests.last()
        pr.status = models.JobStatus.SUCCESS
        pr.title = "New title"
        pr.username = "foobar"
        pr.save()
        self.wait_for_js()
        self.check_js_error()
        self.check_repos()
        self.check_events()

    @SeleniumTester.test_drivers()
    def test_new_branch(self):
        repo, branch = self.create_repo_with_prs()
        url = reverse('ci:view_repo', args=[repo.pk])
        self.get(url)
        self.check_repos()
        self.check_events()
        self.wait_for_js()

        branch2 = utils.create_branch(name="branch2", repo=repo)
        branch2.status = models.JobStatus.SUCCESS
        branch2.save()
        self.wait_for_js()
        self.check_js_error()
        self.check_repos()
        self.check_events()

    @SeleniumTester.test_drivers()
    def test_new_pr(self):
        repo, branch = self.create_repo_with_prs()
        url = reverse('ci:view_repo', args=[repo.pk])
        self.get(url)
        self.check_repos()
        self.check_events()

        pr = utils.create_pr(repo=repo, number=100)
        pr.status = models.JobStatus.RUNNING
        pr.save()
        self.wait_for_js()
        self.check_js_error()
        self.check_repos()
        self.check_events()

    @SeleniumTester.test_drivers()
    def test_close_pr(self):
        repo, branch = self.create_repo_with_prs()
        url = reverse('ci:view_repo', args=[repo.pk])
        self.get(url)
        self.check_repos()
        self.check_events()

        pr = repo.pull_requests.first()
        pr.closed = True
        pr.save()
        self.wait_for_js()
        self.check_js_error()
        self.check_repos()
        self.check_events()

    @SeleniumTester.test_drivers()
    def test_event_update(self):
        ev = self.create_event_with_jobs()
        url = reverse('ci:view_repo', args=[ev.base.branch.repository.pk])
        self.get(url)
        self.check_repos()
        self.check_events()

        ev.status = models.JobStatus.SUCCESS
        ev.save()
        for job in ev.jobs.all():
            job.status = models.JobStatus.SUCCESS
            job.failed_step = "Failed"
            job.invalidated = True
            job.save()
        self.wait_for_js()
        self.check_js_error()
        self.check_repos()
        self.check_events()

    @SeleniumTester.test_drivers()
    def test_new_event(self):
        ev = self.create_event_with_jobs()
        url = reverse('ci:view_repo', args=[ev.base.branch.repository.pk])
        self.get(url)
        self.check_repos()
        self.check_events()
        # need to sleep to make sure creation time is different
        self.wait_for_js()

        self.create_event_with_jobs(commit='4321')
        self.wait_for_js()
        self.check_js_error()
        self.check_repos()
        self.check_events()

    @SeleniumTester.test_drivers()
    def test_event_new_job(self):
        ev = self.create_event_with_jobs()
        url = reverse('ci:view_repo', args=[ev.base.branch.repository.pk])
        self.get(url)
        self.check_repos()
        self.check_events()

        ev = models.Event.objects.first()
        r2 = utils.create_recipe(name="r2")
        ev.save() # to trigger the update
        utils.create_job(event=ev, recipe=r2)
        self.wait_for_js()
        self.check_js_error()
        self.check_repos()
        self.check_events()
