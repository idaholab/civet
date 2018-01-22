
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

from ci import models, ManualEvent
from . import DBTester
from . import utils

class Tests(DBTester.DBTester):
    def setUp(self):
        super(Tests, self).setUp()
        self.create_default_recipes()

    def create_data(self, branch=None, user=None, latest="1"):
        if branch == None:
            branch = self.branch
        if user == None:
            user = self.build_user
        manual = ManualEvent.ManualEvent(user, branch, latest)
        request = self.factory.get('/')
        request.session = {} # the default RequestFactory doesn't have a session
        return manual, request

    def test_bad_branch(self):
        other_branch = utils.create_branch(name="foo", user=self.build_user)
        manual, request = self.create_data(branch=other_branch)
        # Make sure if there is a manual event and there are no recipes for the branch
        # we don't leave anything around
        # This shouldn't create an event or any jobs.
        self.set_counts()
        manual.save(request)
        self.compare_counts()

    def test_bad_user(self):
        other_build_user = utils.create_user(name="bad_build_user")
        manual, request = self.create_data(user=other_build_user)
        # Make sure we only get recipes for the correct build user
        # This shouldn't create an event or any jobs.
        self.set_counts()
        manual.save(request)
        self.compare_counts()

    def test_valid(self):
        manual, request = self.create_data()
        # a valid Manual, should just create an event and 1 jobs
        self.set_counts()
        manual.save(request)
        self.compare_counts(events=1, jobs=1, ready=1, commits=1, active=1, active_repos=1)

        # saving again shouldn't do anything
        self.set_counts()
        manual.save(request)
        self.compare_counts()

    def test_multiple(self):
        manual, request = self.create_data()
        self.set_counts()
        manual.save(request)
        self.compare_counts(events=1, jobs=1, ready=1, commits=1, active=1, active_repos=1)
        # now try another event on the Manual
        # it should just create more jobs
        old_ev = models.Event.objects.first()
        manual, request = self.create_data(latest="10")
        self.set_counts()
        manual.save(request)
        self.compare_counts(events=1, jobs=1, ready=1, commits=1, active=1)
        old_ev.refresh_from_db()
        self.assertEqual(old_ev.status, models.JobStatus.NOT_STARTED)
        self.assertFalse(old_ev.complete)

    def test_recipe(self):
        manual, request = self.create_data()
        self.set_counts()
        manual.save(request)
        self.compare_counts(events=1, jobs=1, ready=1, commits=1, active=1, active_repos=1)

        # now try another event on the Manual but with a new recipe that has the same filename
        manual_recipe = models.Recipe.objects.filter(cause=models.Recipe.CAUSE_MANUAL).latest()
        new_recipe = utils.create_recipe(name="New recipe", user=self.build_user, repo=self.repo, branch=self.branch, cause=models.Recipe.CAUSE_MANUAL)
        new_recipe.filename = manual_recipe.filename
        new_recipe.current = True
        new_recipe.active = True
        new_recipe.save()
        manual_recipe.current = False
        manual_recipe.save()
        self.set_counts()
        manual_recipe.save()
        self.compare_counts()

        # We have a new latest SHA, everything should be created
        manual, request = self.create_data(latest="10")
        self.set_counts()
        manual.save(request)
        self.compare_counts(events=1, jobs=1, ready=1, commits=1, active=1)
        self.assertEqual(manual_recipe.jobs.count(), 1)
        self.assertEqual(new_recipe.jobs.count(), 1)

        # save the same Manual and make sure the jobs haven't changed
        # and no new events were created.
        self.set_counts()
        manual.save(request)
        self.compare_counts()

        # now a new recipe is added that has a different filename
        new_recipe = utils.create_recipe(name="Another New recipe", user=self.build_user, repo=self.repo, branch=self.branch, cause=models.Recipe.CAUSE_MANUAL)
        new_recipe.filename = "Some other filename"
        new_recipe.current = True
        new_recipe.active = True
        new_recipe.save()
        self.set_counts()
        manual.save(request)
        self.compare_counts(jobs=1, ready=1, active=1)

    def test_manual(self):
        manual, request = self.create_data()

        q = models.Recipe.objects.filter(cause=models.Recipe.CAUSE_MANUAL)
        self.assertEqual(q.count(), 1)
        r = q.first()
        r.automatic = models.Recipe.MANUAL
        r.save()
        self.set_counts()
        manual.save(request)
        self.compare_counts(events=1, jobs=1, commits=1, active_repos=1)
        j = models.Job.objects.first()
        self.assertEqual(j.active, False)
        self.assertEqual(j.status, models.JobStatus.ACTIVATION_REQUIRED)

    def test_change_recipe(self):
        manual, request = self.create_data()
        self.set_counts()
        manual.save(request)
        self.compare_counts(events=1, jobs=1, ready=1, commits=1, active=1, active_repos=1)
        # This scenario is one where the event already exists but the
        # for some reason the same event gets called and the recipes have changed.
        # Nothing should change
        manual_recipe = models.Recipe.objects.filter(cause=models.Recipe.CAUSE_MANUAL).latest()
        new_recipe = utils.create_recipe(name="New recipe", user=self.build_user, repo=self.repo, branch=self.branch, cause=models.Recipe.CAUSE_MANUAL)
        new_recipe.filename = manual_recipe.filename
        new_recipe.save()
        manual_recipe.current = False
        manual_recipe.save()

        self.set_counts()
        manual.save(request)
        self.compare_counts()
        self.assertEqual(manual_recipe.jobs.count(), 1)
        self.assertEqual(new_recipe.jobs.count(), 0)

    def test_duplicates(self):
        manual, request = self.create_data()
        self.set_counts()
        manual.save(request)
        self.compare_counts(events=1, jobs=1, ready=1, commits=1, active=1, active_repos=1)

        self.set_counts()
        manual.save(request)
        self.compare_counts()

        manual.force = True
        self.set_counts()
        manual.save(request)
        self.compare_counts(events=1, jobs=1, ready=1, active=1)
        ev = models.Event.objects.first()
        self.assertEqual(ev.duplicates, 1)

        # Try one more time to make sure that the model.Event.objects.get only returns
        # one record
        self.set_counts()
        manual.save(request)
        self.compare_counts(events=1, jobs=1, ready=1, active=1)
        ev = models.Event.objects.first()
        self.assertEqual(ev.duplicates, 2)
