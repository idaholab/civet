
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

from ci import models, PullRequestEvent, GitCommitData
from ci.github import api
from mock import patch
import DBTester
import utils
from django.conf import settings

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

    def create_pr_data(self):
        c1, c1_data, c2, c2_data = self.create_commit_data()
        pr = PullRequestEvent.PullRequestEvent()
        pr.pr_number = 1
        pr.action = PullRequestEvent.PullRequestEvent.OPENED
        pr.build_user = self.build_user
        pr.title = 'PR 1'
        pr.html_url = 'url'
        pr.full_text = ''
        pr.base_commit = c1_data
        pr.head_commit = c2_data
        pr.trigger_user = c2.user().name
        request = self.factory.get('/')
        request.session = {} # the default RequestFactory doesn't have a session
        return c1_data, c2_data, pr, request

    def test_bad_user(self):
        """
        Make sure we only get recipes for the correct build user
        This shouldn't create an event or any jobs.
        """
        c1_data, c2_data, pr, request = self.create_pr_data()
        other_build_user = utils.create_user_with_token(name="bad_build_user")
        pr.build_user = other_build_user
        self.set_counts()
        pr.save(request)
        self.compare_counts()

    def test_valid(self):
        """
        a valid PR, should just create an event, a PR, and 2 jobs
        """
        c1_data, c2_data, pr, request = self.create_pr_data()
        self.set_counts()
        pr.changed_files = ["docs/foo"]
        pr.save(request)
        self.compare_counts(events=1, jobs=2, ready=1, prs=1, active=2, active_repos=1)

        # save the same pull request and make sure the jobs haven't changed
        # and no new events were created.
        self.set_counts()
        pr.save(request)
        self.compare_counts()

        # save the same pull request and make sure the jobs haven't changed
        # and no new events were created.
        self.set_counts()
        pr.save(request)
        self.compare_counts()

        # new sha should create new event and cancel old one
        pr.head_commit.sha = "5678"
        self.set_counts()
        pr.save(request)
        self.compare_counts(jobs=2, ready=1, events=1, commits=1, active=2, canceled=2, events_canceled=1, num_changelog=2, num_events_completed=1, num_jobs_completed=2)

        # should now add the alternative job automatically
        alt = self.set_label_settings()
        pr.changed_files = ["docs/foo", 'other/bar']
        pr.head_commit.sha = "6789"
        self.set_counts()
        pr.save(request)
        self.compare_counts(jobs=3, ready=1, events=1, commits=1, active=3, canceled=2, events_canceled=1, num_changelog=2, num_events_completed=1, num_jobs_completed=2, num_pr_alts=1)
        self.assertEqual(alt[0].jobs.count(), 1)

        # new commit should add the previously added alternate job
        pr.changed_files = []
        pr.head_commit.sha = "789"
        self.set_counts()
        pr.save(request)
        self.compare_counts(jobs=3, ready=1, events=1, commits=1, active=3, canceled=3, events_canceled=1, num_changelog=3, num_events_completed=1, num_jobs_completed=3)
        self.assertEqual(alt[0].jobs.count(), 2)

        # new commit should only add the alt job and its dependency
        pr.changed_files = ["docs/foo"]
        pr.head_commit.sha = "89"
        self.set_counts()
        pr.save(request)
        self.compare_counts(jobs=2, ready=1, events=1, commits=1, active=2, canceled=3, events_canceled=1, num_changelog=3, num_events_completed=1, num_jobs_completed=3)
        self.assertEqual(alt[0].jobs.count(), 3)

    def test_cancel(self):
        c1_data, c2_data, pr, request = self.create_pr_data()
        self.set_counts()
        pr.save(request)
        self.compare_counts(events=1, jobs=2, ready=1, prs=1, active=2, active_repos=1)

        alt_recipe = models.Recipe.objects.filter(cause=models.Recipe.CAUSE_PULL_REQUEST_ALT).first()
        pr_rec = models.PullRequest.objects.first()
        pr_rec.alternate_recipes.add(alt_recipe)
        # now try another event on the PR
        # it should cancel previous events and jobs
        # the alt_recipe job and another pr recipe depend on the same recipe
        # so only one job will be ready
        old_ev = models.Event.objects.first()
        c2_data.sha = '10'
        pr.head_commit = c2_data
        self.set_counts()
        pr.save(request)
        self.compare_counts(jobs=3, ready=1, events=1, commits=1, canceled=2, active=3, num_events_completed=1, num_jobs_completed=2, events_canceled=1, num_changelog=2)
        old_ev.refresh_from_db()
        self.assertEqual(old_ev.status, models.JobStatus.CANCELED)
        self.assertTrue(old_ev.complete)
        new_ev = models.Event.objects.first()

        self.assertEqual(new_ev.status, models.JobStatus.NOT_STARTED)
        self.assertFalse(new_ev.complete)
        for j in new_ev.jobs.all():
            self.assertEqual(j.status, models.JobStatus.NOT_STARTED)
            self.assertFalse(j.complete)

        for j in old_ev.jobs.all():
            self.assertEqual(j.status, models.JobStatus.CANCELED)
            self.assertTrue(j.complete)

        # save the same pull request and make sure the jobs haven't changed
        # and no new events were created.
        self.set_counts()
        pr.save(request)
        self.compare_counts()

    def test_change_recipe(self):
        """
        Try saving the same pull request but the recipe repo has changed.
        This scenario is one where the event already exists but the
        user might have just changed something cosmetic about the PR.
        So we don't change the current recipes on the event or the jobs either.
        But a recipe does get created
        """
        c1_data, c2_data, pr, request = self.create_pr_data()
        c1_data, c2_data, pr, request = self.create_pr_data()
        self.set_counts()
        pr.save(request)
        self.compare_counts(events=1, jobs=2, ready=1, prs=1, active=2, active_repos=1)

        new_recipe = utils.create_recipe(name="New recipe", user=self.build_user, repo=self.repo, branch=self.branch, cause=models.Recipe.CAUSE_PULL_REQUEST)
        pr_recipe = models.Recipe.objects.filter(cause=models.Recipe.CAUSE_PULL_REQUEST).latest()
        new_recipe.filename = pr_recipe.filename
        new_recipe.save()
        for dep in pr_recipe.depends_on.all():
            new_recipe.depends_on.add(dep)
        pr_recipe.current = False
        pr_recipe.save()

        self.set_counts()
        pr.save(request)
        self.compare_counts()

    def test_not_active(self):
        """
        with only one PR active and one not active
        """
        c1_data, c2_data, pr, request = self.create_pr_data()
        pr_recipe = models.Recipe.objects.filter(cause=models.Recipe.CAUSE_PULL_REQUEST).last()
        pr_recipe.active = False
        pr_recipe.save()

        self.set_counts()
        pr.save(request)
        self.compare_counts(events=1, jobs=1, ready=1, active=1, prs=1, active_repos=1)
        ev = models.Event.objects.order_by('-created').first()
        self.assertEqual(ev.jobs.count(), 1)
        self.assertEqual(ev.jobs.filter(ready=False).count(), 0)
        self.assertEqual(ev.jobs.filter(active=False).count(), 0)

    def test_manual(self):
        """
        one PR marked as manual
        """
        c1_data, c2_data, pr, request = self.create_pr_data()
        pr_recipe = models.Recipe.objects.filter(cause=models.Recipe.CAUSE_PULL_REQUEST).last()
        pr_recipe.automatic = models.Recipe.MANUAL
        pr_recipe.save()

        self.set_counts()
        pr.save(request)
        self.compare_counts(events=1, jobs=2, ready=1, active=1, prs=1, active_repos=1)
        ev = models.Event.objects.order_by('-created').first()
        self.assertEqual(ev.jobs.count(), 2)
        self.assertEqual(ev.jobs.filter(ready=False).count(), 1)
        self.assertEqual(ev.jobs.filter(active=False).count(), 1)

    @patch.object(api.GitHubAPI, 'pr_comment')
    @patch.object(api.GitHubAPI, 'is_collaborator')
    def test_authorized_fail(self, mock_is_collaborator, mock_comment):
        """
        Recipe with automatic=authorized
        Try out the case where the user IS NOT a collaborator
        """
        mock_is_collaborator.return_value = False
        c1_data, c2_data, pr, request = self.create_pr_data()
        pr_recipe = models.Recipe.objects.filter(cause=models.Recipe.CAUSE_PULL_REQUEST).last()
        pr_recipe.automatic = models.Recipe.AUTO_FOR_AUTHORIZED
        pr_recipe.save()

        settings.GITHUB_POST_JOB_STATUS = True
        self.set_counts()
        pr.save(request)
        self.compare_counts(events=1, jobs=2, ready=1, active=1, prs=1, active_repos=1)
        ev = models.Event.objects.order_by('-created').first()
        self.assertEqual(ev.jobs.count(), 2)
        self.assertEqual(ev.jobs.filter(ready=False).count(), 1)
        self.assertEqual(ev.jobs.filter(active=False).count(), 1)
        self.assertEqual(mock_comment.call_count, 1)

    @patch.object(api.GitHubAPI, 'is_collaborator')
    def test_authorized_success(self, mock_is_collaborator):
        """
        Recipe with automatic=authorized
        Try out the case where the user IS a collaborator
        """
        mock_is_collaborator.return_value = True
        c1_data, c2_data, pr, request = self.create_pr_data()
        c1_data, c2_data, pr, request = self.create_pr_data()
        pr_recipe = models.Recipe.objects.filter(cause=models.Recipe.CAUSE_PULL_REQUEST).last()
        pr_recipe.automatic = models.Recipe.AUTO_FOR_AUTHORIZED
        pr_recipe.save()

        self.set_counts()
        pr.save(request)
        # one PR depends on the other so only 1 ready
        self.compare_counts(events=1, jobs=2, ready=1, active=2, prs=1, active_repos=1)
        ev = models.Event.objects.order_by('-created').first()
        self.assertEqual(ev.jobs.count(), 2)
        self.assertEqual(ev.jobs.filter(ready=True).count(), 1)
        self.assertEqual(ev.jobs.filter(active=True).count(), 2)

    @patch.object(api.GitHubAPI, 'is_collaborator')
    def test_authorized_no_user(self, mock_is_collaborator):
        """
        Recipe with automatic=authorized
        Try out the case where the user isn't in the database
        """
        mock_is_collaborator.return_value = False
        c1_data, c2_data, pr, request = self.create_pr_data()
        c1_data, c2_data, pr, request = self.create_pr_data()
        pr_recipe = models.Recipe.objects.filter(cause=models.Recipe.CAUSE_PULL_REQUEST).last()
        pr_recipe.automatic = models.Recipe.AUTO_FOR_AUTHORIZED
        pr_recipe.save()
        pr.trigger_user = ""

        self.set_counts()
        pr.save(request)
        # one PR depends on the other so only 1 ready
        self.compare_counts(events=1, jobs=2, ready=1, active=1, prs=1, active_repos=1)
        ev = models.Event.objects.order_by('-created').first()
        self.assertEqual(ev.jobs.count(), 2)
        self.assertEqual(ev.jobs.filter(ready=True).count(), 1)
        self.assertEqual(ev.jobs.filter(active=True).count(), 1)

    @patch.object(api.GitHubAPI, 'is_collaborator')
    def test_authorized_new_user(self, mock_is_collaborator):
        """
        Recipe with automatic=authorized
        Try out the case where the user isn't in the database
        """
        mock_is_collaborator.return_value = False
        c1_data, c2_data, pr, request = self.create_pr_data()
        c1_data, c2_data, pr, request = self.create_pr_data()
        pr_recipe = models.Recipe.objects.filter(cause=models.Recipe.CAUSE_PULL_REQUEST).last()
        pr_recipe.automatic = models.Recipe.AUTO_FOR_AUTHORIZED
        pr_recipe.save()
        pr.trigger_user = "no_exist"

        self.set_counts()
        pr.save(request)
        # one PR depends on the other so only 1 ready
        self.compare_counts(events=1, jobs=2, ready=1, active=1, prs=1, active_repos=1)
        ev = models.Event.objects.order_by('-created').first()
        self.assertEqual(ev.jobs.count(), 2)
        self.assertEqual(ev.jobs.filter(ready=True).count(), 1)
        self.assertEqual(ev.jobs.filter(active=True).count(), 1)

    def test_close(self):
        c1_data, c2_data, pr, request = self.create_pr_data()
        self.set_counts()
        pr.save(request)
        self.compare_counts(events=1, jobs=2, ready=1, prs=1, active=2, active_repos=1)

        self.set_counts()
        pr.action = PullRequestEvent.PullRequestEvent.CLOSED
        pr.save(request)
        self.compare_counts(pr_closed=True)

        self.set_counts()
        pr.pr_number = 1000
        pr.save(request)
        self.compare_counts(pr_closed=True)

    def test_create_pr_alternates(self):
        c1_data, c2_data, pr, request = self.create_pr_data()
        pr.save(request)
        pr_rec = models.PullRequest.objects.latest()

        self.set_counts()
        pr.create_pr_alternates(request, pr_rec)
        self.compare_counts()

        alt_recipe = models.Recipe.objects.filter(cause=models.Recipe.CAUSE_PULL_REQUEST_ALT).first()
        pr_rec.alternate_recipes.add(alt_recipe)
        self.set_counts()
        pr.create_pr_alternates(request, pr_rec)
        self.compare_counts(jobs=1, active=1)

    def test_get_recipes(self):
        alt = self.set_label_settings()
        c1_data, c2_data, pr, request = self.create_pr_data()
        base = models.Recipe.objects.filter(cause=models.Recipe.CAUSE_PULL_REQUEST, depends_on=None)
        self.assertEqual(base.count(), 1)
        base = base.first()
        with_dep = models.Recipe.objects.filter(cause=models.Recipe.CAUSE_PULL_REQUEST).exclude(depends_on=None)
        self.assertEqual(with_dep.count(), 1)
        with_dep = with_dep.first()

        matched = ["DOCUMENTATION"]
        matched_all = True
        c1_data.create()
        recipes = pr._get_recipes(c1_data.commit_record, matched, matched_all)
        self.assertEqual(len(recipes), 2) # The ALT recipe and its dependency
        self.assertIn(alt[0], recipes)
        self.assertIn(base, recipes)

        matched_all = False
        recipes = pr._get_recipes(c1_data.commit_record, matched, matched_all)
        self.assertEqual(len(recipes), 3) # The normal recipes plus the ALT
        self.assertIn(alt[0], recipes)
        self.assertIn(base, recipes)
        self.assertIn(with_dep, recipes)
        self.assertEqual(recipes.count(base), 1)

        matched = []
        recipes = pr._get_recipes(c1_data.commit_record, matched, matched_all)
        self.assertEqual(len(recipes), 2) # Just the normal recipes
        self.assertIn(with_dep, recipes)
        self.assertIn(base, recipes)
        self.assertNotIn(alt[0], recipes)

    def test_get_recipes_with_deps(self):
        self.set_label_settings()
        c1_data, c2_data, pr, request = self.create_pr_data()
        alt = models.Recipe.objects.filter(cause=models.Recipe.CAUSE_PULL_REQUEST_ALT)
        self.assertEqual(alt.count(), 1)
        recipes = pr._get_recipes_with_deps(alt.all())
        self.assertEqual(len(recipes), 2)

    def test_long_titles(self):
        c1_data, c2_data, pr, request = self.create_pr_data()
        pr.title = 'a'*200
        self.set_counts()
        pr.save(request)
        self.compare_counts(events=1, jobs=2, ready=1, prs=1, active=2, active_repos=1)
        pr_rec = models.PullRequest.objects.first()
        self.assertEqual(pr_rec.title, 'a'*120)

    def test_with_only_matched(self):
        # No labels setup, should just do the normal
        c1_data, c2_data, pr, request = self.create_pr_data()
        self.set_counts()
        pr.changed_files = ["docs/foo", 'docs/bar']
        pr.save(request)
        self.compare_counts(events=1, jobs=2, ready=1, prs=1, active=2, active_repos=1)

        # We have labels now, so the new event should only have the matched jobs (and dependencies)
        alt = self.set_label_settings()
        pr.head_commit.sha = "123"
        self.set_counts()
        pr.save(request)
        self.compare_counts(jobs=2, ready=1, events=1, commits=1, active=2, canceled=2, events_canceled=1, num_changelog=2, num_events_completed=1, num_jobs_completed=2, num_pr_alts=1)
        self.assertEqual(alt[0].jobs.count(), 1)

    def test_with_mixed_matched(self):
        # No labels setup, should just do the normal
        c1_data, c2_data, pr, request = self.create_pr_data()
        self.set_counts()
        pr.changed_files = ["docs/foo", 'foo/bar']
        pr.save(request)
        self.compare_counts(events=1, jobs=2, ready=1, prs=1, active=2, active_repos=1)

        # We have labels now, so the new event should only have the default plus the matched
        alt = self.set_label_settings()
        pr.head_commit.sha = "123"
        self.set_counts()
        pr.save(request)
        self.compare_counts(jobs=3, ready=1, events=1, commits=1, active=3, canceled=2, events_canceled=1, num_changelog=2, num_events_completed=1, num_jobs_completed=2, num_pr_alts=1)
        self.assertEqual(alt[0].jobs.count(), 1)

    def test_matched_with_no_labels(self):
        # No labels setup, should just do the normal
        settings.RECIPE_LABEL_ACTIVATION = {"DOCUMENTATION": "^docs/",
          "TUTORIAL": "^tutorials/",
          "EXAMPLES": "^examples/",
        }
        c1_data, c2_data, pr, request = self.create_pr_data()
        self.set_counts()
        pr.changed_files = ["docs/foo", 'docs/bar']
        pr.save(request)
        self.compare_counts(events=1, jobs=2, ready=1, prs=1, active=2, active_repos=1)

    def test_with_no_matched(self):
        # No labels setup, should just do the normal
        c1_data, c2_data, pr, request = self.create_pr_data()
        self.set_counts()
        pr.changed_files = ["bar/foo", 'foo/bar']
        pr.save(request)
        self.compare_counts(events=1, jobs=2, ready=1, prs=1, active=2, active_repos=1)

        # We have labels now, so the new event should only have the default plus the matched
        alt = self.set_label_settings()
        pr.head_commit.sha = "123"
        self.set_counts()
        pr.save(request)
        self.compare_counts(jobs=2, ready=1, events=1, commits=1, active=2, canceled=2, events_canceled=1, num_changelog=2, num_events_completed=1, num_jobs_completed=2)
        self.assertEqual(alt[0].jobs.count(), 0)

    @patch.object(api.GitHubAPI, 'remove_pr_label')
    def test_failed_but_allowed_label(self, mock_label):
        # Make sure any failed but allowed label is removed
        # on pushes
        c1_data, c2_data, pr, request = self.create_pr_data()
        self.set_counts()
        pr.save(request)
        self.compare_counts(events=1, jobs=2, ready=1, prs=1, active=2, active_repos=1)
        # Doesn't get called when a PR is first created
        self.assertEqual(mock_label.call_count, 0)

        # We have labels now, so the new event should only have the default plus the matched
        pr.head_commit.sha = "123"
        self.set_counts()
        pr.save(request)
        self.compare_counts(jobs=2, ready=1, events=1, commits=1, active=2, canceled=2, events_canceled=1, num_changelog=2, num_events_completed=1, num_jobs_completed=2)
        self.assertEqual(mock_label.call_count, 1)
