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
from ci import models, ReleaseEvent, GitCommitData
from ci.tests import DBTester, utils


class Tests(DBTester.DBTester):
    def setUp(self):
        super(Tests, self).setUp()
        self.create_default_recipes()

    def create_data(self):
        commit_data = GitCommitData.GitCommitData(
            self.owner.name,
            self.repo.name,
            self.branch.name,
            "1234",
            "",
            self.build_user.server,
        )
        release = ReleaseEvent.ReleaseEvent()
        release.build_user = self.build_user
        release.full_text = ""
        release.commit = commit_data
        release.release_tag = "1.0"
        release.description = "Release: 1.0"
        return release

    def create_release_recipe(self, name, automatic=models.Recipe.FULL_AUTO):
        recipe = utils.create_recipe(
            name=name,
            user=self.build_user,
            repo=self.repo,
            branch=self.branch,
            cause=models.Recipe.CAUSE_RELEASE,
        )
        recipe.automatic = automatic
        recipe.save()
        return recipe

    def test_no_recipes(self):
        release = self.create_data()
        self.set_counts()
        release.save()
        self.compare_counts()

    def test_valid(self):
        self.create_release_recipe("Release")
        self.create_release_recipe("Release manual", automatic=models.Recipe.MANUAL)
        release = self.create_data()
        self.set_counts()
        release.save()
        # The manual recipe's job requires activation
        self.compare_counts(events=1, commits=1, jobs=2, ready=1, active=1)
        ev = models.Event.objects.order_by("-created").first()
        self.assertEqual(ev.cause, models.Event.RELEASE)
        self.assertEqual(ev.description, "Release: 1.0")
        manual_job = ev.jobs.get(recipe__name="Release manual")
        self.assertFalse(manual_job.active)
        self.assertFalse(manual_job.ready)

        # save again shouldn't do anything
        self.set_counts()
        release.save()
        self.compare_counts()
