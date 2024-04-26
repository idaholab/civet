
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
from ci import models, PushEvent, GitCommitData
from ci.tests import DBTester, utils
from django.test import override_settings
from ci.client import views as client_views
from ci.client import UpdateRemoteStatus
from ci.client.ReadyJobs import get_ready_jobs

import json

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
        return c1_data, c2_data, push

    def test_no_recipes(self):
        # Make sure if there is a push and there are no recipes, we don't leave anything around
        # This shouldn't create an event or any jobs.
        c1_data, c2_data, push = self.create_data()
        c1_data = GitCommitData.GitCommitData("no_exist", "no_exist", "no_exist", "1", "", self.build_user.server)
        push.base_commit = c1_data
        self.set_counts()
        push.save()
        self.compare_counts()

    def test_bad_user(self):
        other_build_user = utils.create_user(name="bad_build_user")
        # Make sure we only get recipes for the correct build user
        # This shouldn't create an event or any jobs.
        c1_data, c2_data, push = self.create_data()
        push.build_user = other_build_user
        self.set_counts()
        push.save()
        self.compare_counts()

    def test_valid(self):
        c1_data, c2_data, push = self.create_data()
        # a valid Push, should just create an event and 2 jobs.
        # 1 job depends on the other so only 1 job should be ready
        self.set_counts()
        push.save()
        self.compare_counts(events=1, jobs=2, ready=1, active=2, active_repos=1)

        # save again shouldn't do anything
        self.set_counts()
        push.save()
        self.compare_counts()

    def test_multiple(self):
        c1_data, c2_data, push = self.create_data()
        self.set_counts()
        push.save()
        self.compare_counts(events=1, jobs=2, ready=1, active=2, active_repos=1)
        # now try another event on the Push
        # it should just create more jobs
        old_ev = models.Event.objects.first()
        c2_data.sha = '10'
        push.head_commit = c2_data
        self.set_counts()
        push.save()
        self.compare_counts(events=1, jobs=2, ready=1, commits=1, active=2)
        old_ev.refresh_from_db()
        self.assertEqual(old_ev.status, models.JobStatus.NOT_STARTED)
        self.assertFalse(old_ev.complete)

    def test_manual(self):
        c1_data, c2_data, push = self.create_data()
        q = models.Recipe.objects.filter(cause=models.Recipe.CAUSE_PUSH)
        self.assertEqual(q.count(), 2)
        r = q.exclude(depends_on=None).first()
        r.active = False
        r.save()
        r = q.exclude(pk=r.pk).first()
        r.automatic = models.Recipe.MANUAL
        r.save()
        self.set_counts()
        push.save()
        self.compare_counts(events=1, jobs=1, active_repos=1)
        j = models.Job.objects.first()
        self.assertEqual(j.active, False)
        self.assertEqual(j.status, models.JobStatus.ACTIVATION_REQUIRED)

    def test_recipe(self):
        c1_data, c2_data, push = self.create_data()
        self.set_counts()
        push.save()
        self.compare_counts(events=1, jobs=2, ready=1, active=2, active_repos=1)
        # now try another event on the Push but with a new recipe.
        push_recipe = models.Recipe.objects.filter(cause=models.Recipe.CAUSE_PUSH).latest()
        new_recipe = utils.create_recipe(name="New recipe",
                user=self.build_user,
                repo=self.repo,
                branch=self.branch,
                cause=models.Recipe.CAUSE_PUSH)
        new_recipe.filename = push_recipe.filename
        new_recipe.save()
        push_recipe.current = False
        push_recipe.save()
        c2_data.sha = '10'
        push.head_commit = c2_data
        self.set_counts()
        push.save()
        self.compare_counts(events=1, jobs=2, ready=2, commits=1, active=2)

        # save the same push and make sure the jobs haven't changed
        # and no new events were created.
        self.set_counts()
        push.save()
        self.compare_counts()

    def test_change_recipe(self):
        c1_data, c2_data, push = self.create_data()
        self.set_counts()
        push.save()
        self.compare_counts(events=1, jobs=2, ready=1, active=2, active_repos=1)
        # This scenario is one where the event already exists but
        # for some reason the same push event gets called and the recipes have changed.
        # Nothing should have changed

        push_recipe = models.Recipe.objects.filter(cause=models.Recipe.CAUSE_PUSH).latest()
        new_recipe = utils.create_recipe(name="New recipe",
                user=self.build_user,
                repo=self.repo,
                branch=self.branch,
                cause=models.Recipe.CAUSE_PUSH)
        new_recipe.filename = push_recipe.filename
        new_recipe.save()
        push_recipe.current = False
        push_recipe.save()
        self.assertEqual(push_recipe.jobs.count(), 1)

        self.set_counts()
        push.save()
        self.compare_counts()
        push_recipe.refresh_from_db()
        new_recipe.refresh_from_db()
        self.assertEqual(push_recipe.jobs.count(), 1)
        self.assertEqual(new_recipe.jobs.count(), 0)

    def test_save(self):
        c1_data, c2_data, push = self.create_data()
        base = models.Recipe.objects.filter(cause=models.Recipe.CAUSE_PUSH, depends_on=None)
        self.assertEqual(base.count(), 1)
        base = base.first()
        with_dep = models.Recipe.objects.filter(cause=models.Recipe.CAUSE_PUSH).exclude(depends_on=None)
        self.assertEqual(with_dep.count(), 1)
        with_dep = with_dep.first()
        self.assertEqual(with_dep.depends_on.first(), base)

    def test_auto_cancel_on_push(self):
        c1_data, c2_data, push = self.create_data()
        push_rs = models.Recipe.objects.filter(cause=models.Recipe.CAUSE_PUSH)
        self.assertEqual(push_rs.count(), 2)
        push_first = push_rs.first()
        push_first.auto_cancel_on_push = True
        push_first.save()
        self.set_counts()
        push.save()
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
        push.save()
        self.compare_counts(events=1,
                jobs=2,
                ready=1,
                commits=1,
                active=2,
                canceled=1,
                events_canceled=1,
                num_changelog=1,
                num_jobs_completed=1,
                num_events_completed=1,
                active_branches=1)
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
        push.save()
        self.compare_counts(events=1, jobs=2, ready=1, commits=1, active=2)

    def get_ready_job_pks(self, expected):
        ready_pks = []
        for job in get_ready_jobs():
            ready_pks.append(job.pk)
        self.assertEqual(len(ready_pks), expected)
        return ready_pks

    @override_settings(INSTALLED_GITSERVERS=[utils.github_config(repo_settings={"owner/repo":
        {"branch_settings": {"devel": {"auto_cancel_push_events_except_current": True}}}})])
    def test_auto_cancel_except_current(self):
        """
        This scenario is one where an event exists on the branch, and the branch
        is configured to be auto_cancel_except_current
        Another event comes along and we make sure the current event is not cancelled
        (if it is running) and the new event jobs won't run before the current event.
        Then another event comes in and the second event gets cancelled but the original
        event doesn't.
        """
        c1_data, c2_data, push = self.create_data()
        push_rs = models.Recipe.objects.filter(cause=models.Recipe.CAUSE_PUSH)
        # remove the dependencies to make the testing easier
        for r in push_rs.all():
            r.depends_on.clear()
        self.assertEqual(push_rs.count(), 2)
        push_last= push_rs.last()
        push_last.auto_cancel_on_push = True
        push_last.save()
        self.set_counts()
        push.save()
        self.compare_counts(events=1, jobs=2, ready=2, active=2, active_repos=1)
        e0 = models.Event.objects.latest()
        self.assertEqual(e0.status, models.JobStatus.NOT_STARTED)
        self.assertFalse(e0.complete)
        self.assertEqual(e0.base.branch.status, models.JobStatus.NOT_STARTED)

        # We have an event that isn't running yet. So when a new event comes
        # in we can cancel it.
        e0 = models.Event.objects.latest()
        e0.save()
        j0 = e0.jobs.filter(recipe__auto_cancel_on_push=True).first()
        j1 = e0.jobs.filter(recipe__auto_cancel_on_push=False).first()
        ready_pks = self.get_ready_job_pks(2)

        c2_data.sha = '10'
        push.head_commit = c2_data
        self.set_counts()
        push.save()
        self.compare_counts(events=1, jobs=2, ready=2, commits=1, active=2, canceled=1, num_changelog=1, num_jobs_completed=1)
        e0.refresh_from_db()
        self.assertEqual(e0.jobs.count(), 2)
        js_status = sorted([j.status for j in e0.jobs.all()])
        self.assertEqual([models.JobStatus.NOT_STARTED, models.JobStatus.CANCELED], js_status)
        self.assertEqual(e0.status, models.JobStatus.NOT_STARTED)
        self.assertFalse(e0.complete)
        self.assertEqual(e0.base.branch.status, models.JobStatus.NOT_STARTED)
        ready_pks = self.get_ready_job_pks(3)
        self.assertIn(j1.pk, ready_pks)
        self.assertNotIn(j0.pk, ready_pks)

        # We set this new event to running so that it becomes the "current" event
        # and won't get cancelled.
        e0 = models.Event.objects.latest()
        j0 = e0.jobs.filter(recipe__auto_cancel_on_push=True).first()
        j0.status = models.JobStatus.RUNNING
        j0.save()
        j1 = e0.jobs.filter(recipe__auto_cancel_on_push=False).first()
        e0.status = models.JobStatus.RUNNING
        e0.save()
        ready_pks = self.get_ready_job_pks(2)
        self.assertIn(j1.pk, ready_pks)

        c2_data.sha = '100'
        push.head_commit = c2_data
        self.set_counts()
        push.save()
        self.compare_counts(events=1, jobs=2, ready=2, commits=1, active=2)
        e0.refresh_from_db()
        self.assertEqual(e0.jobs.count(), 2)
        js_status = sorted([j.status for j in e0.jobs.all()])
        self.assertEqual([models.JobStatus.NOT_STARTED, models.JobStatus.RUNNING], js_status)
        self.assertEqual(e0.status, models.JobStatus.RUNNING)
        self.assertFalse(e0.complete)
        self.assertEqual(e0.base.branch.status, models.JobStatus.NOT_STARTED)
        ready_pks = self.get_ready_job_pks(4)
        self.assertIn(j1.pk, ready_pks)
        self.assertNotIn(j0.pk, ready_pks)

        e1 = models.Event.objects.latest()
        self.assertEqual(e1.status, models.JobStatus.NOT_STARTED)
        self.assertFalse(e1.complete)

        j2 = e1.jobs.filter(recipe__auto_cancel_on_push=True).first()
        j3 = e1.jobs.filter(recipe__auto_cancel_on_push=False).first()
        self.assertIn(j2.pk, ready_pks)
        self.assertIn(j3.pk, ready_pks)

        # Set this new event to running, it should still get
        # cancelled when a newer event comes in.
        e1.status = models.JobStatus.RUNNING
        e1.save()

        c2_data.sha = '1000'
        push.head_commit = c2_data
        self.set_counts()
        push.save()
        self.compare_counts(events=1,
                jobs=2,
                ready=2,
                commits=1,
                active=2,
                canceled=1,
                num_changelog=1,
                num_jobs_completed=1,
                )

        e1.refresh_from_db()
        self.assertEqual(e1.status, models.JobStatus.RUNNING)
        self.assertFalse(e1.complete) # One of the jobs still needs to run
        js_status = sorted([j.status for j in e1.jobs.all()])
        self.assertEqual([models.JobStatus.NOT_STARTED, models.JobStatus.CANCELED], js_status)

        e2 = models.Event.objects.latest()
        self.assertEqual(e2.status, models.JobStatus.NOT_STARTED)
        self.assertFalse(e2.complete)

        ready_pks = self.get_ready_job_pks(5)
        self.assertNotIn(j0.pk, ready_pks)
        self.assertIn(j1.pk, ready_pks)
        self.assertNotIn(j2.pk, ready_pks)
        j2.refresh_from_db()
        self.assertEqual(j2.status, models.JobStatus.CANCELED)
        self.assertIn(j3.pk, ready_pks)
        for j in e2.jobs.all():
            self.assertIn(j.pk, ready_pks)

    @override_settings(INSTALLED_GITSERVERS=[utils.github_config(repo_settings={"owner/repo":
        {"branch_settings": {"devel": {"auto_cancel_push_events_except_current": True,
            "auto_uncancel_previous_event": True,}}}})])
    def test_auto_uncancel_event(self):
        """
        E0 - starts running
        E1 - waits for E0 to finish
        E2 - waits for E0 to finish, cancels E1
            E0 is still running but clients start on E2 which gets
            a job failure. Uncancels E1.
        E3 - waits for E0 to finish. Cancels E2 and E1.
            At this point E3 will eventually fail. If E0 is
            still running then it needs to see that E2 is already failed so there is no need
            to uncancel. Instead, it needs to uncancel E1.
        """
        print("Branch: %s" % self.branch)
        c1_data, c2_data, push = self.create_data()
        push_rs = models.Recipe.objects.filter(cause=models.Recipe.CAUSE_PUSH)
        # remove the dependencies to make the testing easier
        for r in push_rs.all():
            r.depends_on.clear()
            r.auto_cancel_on_push = True
            r.save()
        self.assertEqual(push_rs.count(), 2)
        self.set_counts()
        push.save()
        self.compare_counts(events=1, jobs=2, ready=2, active=2, active_repos=1)
        e0 = models.Event.objects.latest()
        e0.status = models.JobStatus.RUNNING
        e0.complete = False
        e0.save()

        # We have an event that isn't running yet. So when a new event comes
        # in we can cancel it.
        # E0 is running
        for j in e0.jobs.all():
            utils.update_job(j, status=models.JobStatus.RUNNING)

        # A new event E1 comes in. E0 is still running so nothing is canceled.
        # Jobs on E1 can be run though
        c2_data.sha = '3'
        push.head_commit = c2_data
        self.set_counts()
        push.save()
        self.compare_counts(events=1, jobs=2, ready=2, commits=1, active=2)
        e0.refresh_from_db()
        for j in e0.jobs.all():
            self.assertEqual(j.status, models.JobStatus.RUNNING)

        e1 = models.Event.objects.latest()
        for j in e1.jobs.all():
            self.assertEqual(j.status, models.JobStatus.NOT_STARTED)
            self.assertEqual(j.ready, True)

        # A new event E2 comes in. E0 is still running so we need to cancel E1.
        # Jobs on E2 can be run.
        c2_data.sha = '4'
        push.head_commit = c2_data
        self.set_counts()
        push.save()
        self.compare_counts(events=1,
                jobs=2,
                ready=2,
                commits=1,
                active=2,
                active_branches=1,
                canceled=2,
                events_canceled=1,
                num_events_completed=1,
                num_jobs_completed=2,
                num_changelog=2)
        e0.refresh_from_db()
        for j in e0.jobs.all():
            self.assertEqual(j.status, models.JobStatus.RUNNING)

        e1.refresh_from_db()
        for j in e1.jobs.all():
            self.assertEqual(j.status, models.JobStatus.CANCELED)
            self.assertEqual(j.complete, True)

        e2 = models.Event.objects.latest()
        for j in e2.jobs.all():
            self.assertEqual(j.status, models.JobStatus.NOT_STARTED)
            self.assertEqual(j.complete, False)

        # Make a job failure on E2. Should uncancel E1.
        e2_j0 = e2.jobs.first()
        e2_j1 = e2.jobs.last()
        utils.update_job(e2_j0, status=models.JobStatus.FAILED, complete=True)
        self.set_counts()
        UpdateRemoteStatus.start_canceled_on_fail(e2_j0)
        self.compare_counts(active_branches=-1,
                canceled=-2,
                events_canceled=-1,
                invalidated=2,
                num_changelog=2,
                num_events_completed=-1,
                num_jobs_completed=-2,
                )
        e0.refresh_from_db()
        for j in e0.jobs.all():
            self.assertEqual(j.status, models.JobStatus.RUNNING)

        e1.refresh_from_db()
        for j in e1.jobs.all():
            self.assertEqual(j.status, models.JobStatus.NOT_STARTED)
            self.assertEqual(j.complete, False)

        # A new event E3 comes in. E0, E1, and E2 all are running
        # so we need to cancel E1 and E2.
        # Jobs on E3 can be run.
        c2_data.sha = '5'
        push.head_commit = c2_data
        self.set_counts()
        push.save()
        self.compare_counts(events=1,
                jobs=2,
                ready=2,
                commits=1,
                active=2,
                active_branches=1,
                canceled=3,
                events_canceled=1,
                num_events_completed=2,
                num_jobs_completed=3,
                num_changelog=3)

        e0.refresh_from_db()
        for j in e0.jobs.all():
            self.assertEqual(j.status, models.JobStatus.RUNNING)

        e1.refresh_from_db()
        for j in e1.jobs.all():
            self.assertEqual(j.status, models.JobStatus.CANCELED)
            self.assertEqual(j.complete, True)

        e2.refresh_from_db()
        e2_j0.refresh_from_db()
        self.assertEqual(e2_j0.status, models.JobStatus.FAILED)
        self.assertEqual(e2_j0.complete, True)
        e2_j1.refresh_from_db()
        self.assertEqual(e2_j1.status, models.JobStatus.CANCELED)
        self.assertEqual(e2_j1.complete, True)

        e3 = models.Event.objects.latest()
        for j in e3.jobs.all():
            self.assertEqual(j.status, models.JobStatus.NOT_STARTED)
            self.assertEqual(j.complete, False)

        # Make a job failure on E3. Should uncancel E1 and leave E2 canceled.
        e3_j0 = e3.jobs.first()
        utils.update_job(e3_j0, status=models.JobStatus.FAILED, complete=True)
        self.set_counts()
        UpdateRemoteStatus.start_canceled_on_fail(e3_j0)
        self.compare_counts(active_branches=-1,
                canceled=-2,
                events_canceled=-1,
                num_changelog=2,
                num_events_completed=-1,
                num_jobs_completed=-2,
                )
        e0.refresh_from_db()
        for j in e0.jobs.all():
            self.assertEqual(j.status, models.JobStatus.RUNNING)

        e1.refresh_from_db()
        for j in e1.jobs.all():
            self.assertEqual(j.status, models.JobStatus.NOT_STARTED)
            self.assertEqual(j.complete, False)

        e2.refresh_from_db()
        e2_j0.refresh_from_db()
        self.assertEqual(e2_j0.status, models.JobStatus.FAILED)
        self.assertEqual(e2_j0.complete, True)
        e2_j1.refresh_from_db()
        self.assertEqual(e2_j1.status, models.JobStatus.CANCELED)
        self.assertEqual(e2_j1.complete, True)
