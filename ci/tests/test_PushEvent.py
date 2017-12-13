
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

from ci import models, PushEvent, GitCommitData
import DBTester
import utils

class Tests(DBTester.DBTester):
    def setUp(self):
        super(Tests, self).setUp()
        self.create_default_recipes()

    def create_commit_data(self):
        c1 = utils.create_commit(sha='1', branch=self.branch, user=self.owner)
        c2 = utils.create_commit(sha='2', branch=self.branch, user=self.owner)
        c1_data = GitCommitData.GitCommitData(self.owner.name, c1.repo().name, c1.branch.name, c1.sha, '', c1.server())
        c2_data = GitCommitData.GitCommitData(self.owner.name, c2.repo().name, c2.branch.name, c2.sha, '', c2.server())
        return c1, c1_data, c2, c2_data

    def create_data(self):
        c1, c1_data, c2, c2_data = self.create_commit_data()
        push = PushEvent.PushEvent()
        push.build_user = self.build_user
        push.full_text = ''
        push.base_commit = c1_data
        push.head_commit = c2_data
        request = self.factory.get('/')
        request.session = {} # the default RequestFactory doesn't have a session
        return c1_data, c2_data, push, request

    def test_no_recipes(self):
        # Make sure if there is a push and there are no recipes, we don't leave anything around
        # This shouldn't create an event or any jobs.
        c1_data, c2_data, push, request = self.create_data()
        c1_data = GitCommitData.GitCommitData("no_exist", "no_exist", "no_exist", "1", "", self.build_user.server)
        push.base_commit = c1_data
        self.set_counts()
        push.save(request)
        self.compare_counts()

    def test_bad_user(self):
        other_build_user = utils.create_user(name="bad_build_user")
        # Make sure we only get recipes for the correct build user
        # This shouldn't create an event or any jobs.
        c1_data, c2_data, push, request = self.create_data()
        push.build_user = other_build_user
        self.set_counts()
        push.save(request)
        self.compare_counts()

    def test_valid(self):
        c1_data, c2_data, push, request = self.create_data()
        # a valid Push, should just create an event and 2 jobs.
        # 1 job depends on the other so only 1 job should be ready
        self.set_counts()
        push.save(request)
        self.compare_counts(events=1, jobs=2, ready=1, active=2, active_repos=1)

        # save again shouldn't do anything
        self.set_counts()
        push.save(request)
        self.compare_counts()

    def test_multiple(self):
        c1_data, c2_data, push, request = self.create_data()
        self.set_counts()
        push.save(request)
        self.compare_counts(events=1, jobs=2, ready=1, active=2, active_repos=1)
        # now try another event on the Push
        # it should just create more jobs
        old_ev = models.Event.objects.first()
        c2_data.sha = '10'
        push.head_commit = c2_data
        self.set_counts()
        push.save(request)
        self.compare_counts(events=1, jobs=2, ready=1, commits=1, active=2)
        old_ev.refresh_from_db()
        self.assertEqual(old_ev.status, models.JobStatus.NOT_STARTED)
        self.assertFalse(old_ev.complete)

    def test_recipe(self):
        c1_data, c2_data, push, request = self.create_data()
        self.set_counts()
        push.save(request)
        self.compare_counts(events=1, jobs=2, ready=1, active=2, active_repos=1)
        # now try another event on the Push but with a new recipe.
        push_recipe = models.Recipe.objects.filter(cause=models.Recipe.CAUSE_PUSH).latest()
        new_recipe = utils.create_recipe(name="New recipe", user=self.build_user, repo=self.repo, branch=self.branch, cause=models.Recipe.CAUSE_PUSH)
        new_recipe.filename = push_recipe.filename
        new_recipe.save()
        push_recipe.current = False
        push_recipe.save()
        c2_data.sha = '10'
        push.head_commit = c2_data
        self.set_counts()
        push.save(request)
        self.compare_counts(events=1, jobs=2, ready=2, commits=1, active=2)

        # save the same push and make sure the jobs haven't changed
        # and no new events were created.
        self.set_counts()
        push.save(request)
        self.compare_counts()

    def test_change_recipe(self):
        c1_data, c2_data, push, request = self.create_data()
        self.set_counts()
        push.save(request)
        self.compare_counts(events=1, jobs=2, ready=1, active=2, active_repos=1)
        # This scenario is one where the event already exists but
        # for some reason the same push event gets called and the recipes have changed.
        # Nothing should have changed

        push_recipe = models.Recipe.objects.filter(cause=models.Recipe.CAUSE_PUSH).latest()
        new_recipe = utils.create_recipe(name="New recipe", user=self.build_user, repo=self.repo, branch=self.branch, cause=models.Recipe.CAUSE_PUSH)
        new_recipe.filename = push_recipe.filename
        new_recipe.save()
        push_recipe.current = False
        push_recipe.save()
        self.assertEqual(push_recipe.jobs.count(), 1)

        self.set_counts()
        push.save(request)
        self.compare_counts()
        push_recipe.refresh_from_db()
        new_recipe.refresh_from_db()
        self.assertEqual(push_recipe.jobs.count(), 1)
        self.assertEqual(new_recipe.jobs.count(), 0)

    def test_save(self):
        c1_data, c2_data, push, request = self.create_data()
        base = models.Recipe.objects.filter(cause=models.Recipe.CAUSE_PUSH, depends_on=None)
        self.assertEqual(base.count(), 1)
        base = base.first()
        with_dep = models.Recipe.objects.filter(cause=models.Recipe.CAUSE_PUSH).exclude(depends_on=None)
        self.assertEqual(with_dep.count(), 1)
        with_dep = with_dep.first()
        self.assertEqual(with_dep.depends_on.first(), base)

    def test_auto_cancel_on_push(self):
        c1_data, c2_data, push, request = self.create_data()
        push_rs = models.Recipe.objects.filter(cause=models.Recipe.CAUSE_PUSH)
        self.assertEqual(push_rs.count(), 2)
        push_first = push_rs.first()
        push_first.auto_cancel_on_push = True
        push_first.save()
        self.set_counts()
        push.save(request)
        self.compare_counts(events=1, jobs=2, ready=1, active=2, active_repos=1)
        old_ev = models.Event.objects.latest()
        self.assertEqual(old_ev.status, models.JobStatus.NOT_STARTED)
        self.assertFalse(old_ev.complete)
        self.assertEqual(old_ev.base.branch.status, models.JobStatus.NOT_STARTED)
        # This scenario is one where an event exists on the branch, with one job
        # set to auto_cancel_on_push.
        # Then another event comes along on the branch, the first job should be canceled.

        old_ev = models.Event.objects.latest()
        c2_data.sha = '10'
        push.head_commit = c2_data
        self.set_counts()
        push.save(request)
        self.compare_counts(events=1, jobs=2, ready=1, commits=1, active=2, canceled=1, events_canceled=1, num_changelog=1, num_jobs_completed=1, num_events_completed=1, active_branches=1)
        push_first.refresh_from_db()
        self.assertEqual(push_first.jobs.count(), 2)
        js_status = sorted([j.status for j in push_first.jobs.all()])
        self.assertEqual([models.JobStatus.NOT_STARTED, models.JobStatus.CANCELED], js_status)
        old_ev.refresh_from_db()
        self.assertEqual(old_ev.status, models.JobStatus.CANCELED)
        self.assertTrue(old_ev.complete)
        self.assertEqual(old_ev.base.branch.status, models.JobStatus.CANCELED)

        # A finished job shouldn't be canceled
        j = push_first.jobs.get(status=models.JobStatus.NOT_STARTED)
        j.status = models.JobStatus.FAILED
        j.complete = True
        j.save()
        c2_data.sha = '11'
        push.head_commit = c2_data
        self.set_counts()
        push.save(request)
        self.compare_counts(events=1, jobs=2, ready=1, commits=1, active=2)
