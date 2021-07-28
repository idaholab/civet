
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
from django.test import TestCase, Client
from django.conf import settings
from ci import models
from ci.tests import utils
from django.test.client import RequestFactory

class DBCompare(object):
    def create_default_recipes(self, server_type=settings.GITSERVER_GITHUB):
        self.set_counts()
        self.server = utils.create_git_server(host_type=server_type)
        self.build_user = utils.create_user_with_token(name="moosebuild", server=self.server)
        self.owner = utils.create_user(name="owner", server=self.server)
        self.repo = utils.create_repo(name="repo", user=self.owner)
        self.branch = utils.create_branch(name="devel", repo=self.repo)
        pr = utils.create_recipe(name="PR Base", user=self.build_user, repo=self.repo)
        pr1 = utils.create_recipe(name="PR With Dep", user=self.build_user, repo=self.repo)
        pr1.depends_on.add(pr)
        push = utils.create_recipe(name="Push Base", user=self.build_user, repo=self.repo, branch=self.branch, cause=models.Recipe.CAUSE_PUSH)
        push1 = utils.create_recipe(name="Push With Dep", user=self.build_user, repo=self.repo, branch=self.branch, cause=models.Recipe.CAUSE_PUSH)
        push1.depends_on.add(push)
        alt_pr = utils.create_recipe(name="Alt PR with dep", user=self.build_user, repo=self.repo, cause=models.Recipe.CAUSE_PULL_REQUEST_ALT)
        alt_pr.depends_on.add(pr)

        utils.create_recipe(name="Manual", user=self.build_user, repo=self.repo, branch=self.branch, cause=models.Recipe.CAUSE_MANUAL)
        self.compare_counts(recipes=6,
            deps=3,
            current=6,
            num_push_recipes=2,
            num_pr_recipes=2,
            num_manual_recipes=1,
            num_pr_alt_recipes=1,
            users=2,
            repos=1,
            branches=1,
            )

    def recipe_deps_count(self):
        count = 0
        for r in models.Recipe.objects.exclude(depends_on=None).prefetch_related("depends_on").all():
            count += r.depends_on.count()
        return count

    def pr_alternates_count(self):
        count = 0
        for r in models.PullRequest.objects.exclude(alternate_recipes=None).prefetch_related("alternate_recipes").all():
            count += r.alternate_recipes.count()
        return count

    def repo_prefs_count(self):
        count = 0
        for u in models.GitUser.objects.all():
            count += u.preferred_repos.count()
        return count

    def set_counts(self):
        self.num_jobs = models.Job.objects.count()
        self.num_jobs_ready = models.Job.objects.filter(ready=True).count()
        self.num_jobs_active = models.Job.objects.filter(active=True).count()
        self.num_events = models.Event.objects.count()
        self.num_recipes = models.Recipe.objects.count()
        self.num_recipe_deps = self.recipe_deps_count()
        self.num_current = models.Recipe.objects.filter(current=True).count()
        self.repo_sha = models.RecipeRepository.load().sha
        self.num_users = models.GitUser.objects.count()
        self.num_repos = models.Repository.objects.count()
        self.num_active_repos = models.Repository.objects.filter(active=True).count()
        self.num_branches = models.Branch.objects.count()
        self.num_active_branches = models.Branch.objects.exclude(status=models.JobStatus.NOT_STARTED).count()
        self.num_commits = models.Commit.objects.count()
        self.num_prs = models.PullRequest.objects.count()
        self.num_push_recipes = models.Recipe.objects.filter(cause=models.Recipe.CAUSE_PUSH).count()
        self.num_pr_recipes = models.Recipe.objects.filter(cause=models.Recipe.CAUSE_PULL_REQUEST).count()
        self.num_manual_recipes = models.Recipe.objects.filter(cause=models.Recipe.CAUSE_MANUAL).count()
        self.num_pr_alt_recipes = models.Recipe.objects.filter(cause=models.Recipe.CAUSE_PULL_REQUEST_ALT).count()
        self.num_release_recipes = models.Recipe.objects.filter(cause=models.Recipe.CAUSE_RELEASE).count()
        self.num_canceled = models.Job.objects.filter(status=models.JobStatus.CANCELED).count()
        self.num_events_canceled = models.Event.objects.filter(status=models.JobStatus.CANCELED).count()
        self.num_invalidated = models.Job.objects.filter(invalidated=True).count()
        self.num_steps = models.Step.objects.count()
        self.num_step_envs = models.StepEnvironment.objects.count()
        self.num_recipe_envs = models.RecipeEnvironment.objects.count()
        self.num_prestep = models.PreStepSource.objects.count()
        self.num_pr_alt_count = self.pr_alternates_count()
        self.num_repo_prefs_count = self.repo_prefs_count()
        self.num_clients = models.Client.objects.count()
        self.num_changelog = models.JobChangeLog.objects.count()
        self.num_events_completed = models.Event.objects.filter(complete=True).count()
        self.num_jobs_completed = models.Job.objects.filter(complete=True).count()
        self.num_viewable_teams = models.RecipeViewableByTeam.objects.count()
        self.num_badges = models.RepositoryBadge.objects.count()

    def compare_counts(self, jobs=0, ready=0, events=0, recipes=0, deps=0, pr_closed=False,
        current=0, sha_changed=False, users=0, repos=0, branches=0, commits=0,
        prs=0, num_push_recipes=0, num_pr_recipes=0, num_manual_recipes=0,
        num_pr_alt_recipes=0, canceled=0, invalidated=0, active=0,
        num_steps=0, num_step_envs=0, num_recipe_envs=0, num_prestep=0,
        num_pr_alts=0, active_repos=0, active_branches=0, repo_prefs=0,
        num_clients=0, events_canceled=0, num_changelog=0,
        num_jobs_completed=0, num_events_completed=0,
        num_release_recipes=0, badges=0,
        viewable_teams=0):
        self.assertEqual(self.num_jobs + jobs, models.Job.objects.count())
        self.assertEqual(self.num_jobs_ready + ready, models.Job.objects.filter(ready=True).count())
        self.assertEqual(self.num_jobs_active + active, models.Job.objects.filter(active=True).count())
        self.assertEqual(self.num_events + events, models.Event.objects.count())
        self.assertEqual(self.num_recipes + recipes, models.Recipe.objects.count())
        self.assertEqual(self.num_recipe_deps + deps, self.recipe_deps_count())
        self.assertEqual(self.num_current + current, models.Recipe.objects.filter(current=True).count())
        self.assertEqual(self.num_users + users, models.GitUser.objects.count())
        self.assertEqual(self.num_repos + repos, models.Repository.objects.count())
        self.assertEqual(self.num_active_repos + active_repos, models.Repository.objects.filter(active=True).count())
        self.assertEqual(self.num_branches + branches, models.Branch.objects.count())
        self.assertEqual(self.num_active_branches + active_branches, models.Branch.objects.exclude(status=models.JobStatus.NOT_STARTED).count())
        self.assertEqual(self.num_commits + commits, models.Commit.objects.count())
        self.assertEqual(self.num_prs + prs, models.PullRequest.objects.count())
        self.assertEqual(self.num_push_recipes + num_push_recipes, models.Recipe.objects.filter(cause=models.Recipe.CAUSE_PUSH).count())
        self.assertEqual(self.num_pr_recipes + num_pr_recipes, models.Recipe.objects.filter(cause=models.Recipe.CAUSE_PULL_REQUEST).count())
        self.assertEqual(self.num_manual_recipes + num_manual_recipes, models.Recipe.objects.filter(cause=models.Recipe.CAUSE_MANUAL).count())
        self.assertEqual(self.num_pr_alt_recipes + num_pr_alt_recipes,  models.Recipe.objects.filter(cause=models.Recipe.CAUSE_PULL_REQUEST_ALT).count())
        self.assertEqual(self.num_release_recipes + num_release_recipes,  models.Recipe.objects.filter(cause=models.Recipe.CAUSE_RELEASE).count())
        self.assertEqual(self.num_canceled + canceled, models.Job.objects.filter(status=models.JobStatus.CANCELED).count())
        self.assertEqual(self.num_events_canceled + events_canceled, models.Event.objects.filter(status=models.JobStatus.CANCELED).count())
        self.assertEqual(self.num_invalidated + invalidated, models.Job.objects.filter(invalidated=True).count())
        self.assertEqual(self.num_steps + num_steps, models.Step.objects.count())
        self.assertEqual(self.num_step_envs + num_step_envs, models.StepEnvironment.objects.count())
        self.assertEqual(self.num_recipe_envs + num_recipe_envs, models.RecipeEnvironment.objects.count())
        self.assertEqual(self.num_prestep + num_prestep, models.PreStepSource.objects.count())
        self.assertEqual(self.num_pr_alt_count + num_pr_alts, self.pr_alternates_count())
        self.assertEqual(self.num_repo_prefs_count+ repo_prefs, self.repo_prefs_count())
        self.assertEqual(self.num_clients + num_clients, models.Client.objects.count())
        self.assertEqual(self.num_changelog + num_changelog, models.JobChangeLog.objects.count())
        self.assertEqual(self.num_events_completed + num_events_completed, models.Event.objects.filter(complete=True).count())
        self.assertEqual(self.num_jobs_completed + num_jobs_completed, models.Job.objects.filter(complete=True).count())
        self.assertEqual(self.num_viewable_teams + viewable_teams, models.RecipeViewableByTeam.objects.count())
        self.assertEqual(self.num_badges + badges, models.RepositoryBadge.objects.count())

        if sha_changed:
            self.assertNotEqual(self.repo_sha, models.RecipeRepository.load().sha)
        else:
            self.assertEqual(self.repo_sha, models.RecipeRepository.load().sha)

        if models.Event.objects.exists():
            ev = models.Event.objects.latest()
            if ev.pull_request:
                self.assertEqual(ev.pull_request.closed, pr_closed)


    def set_label_on_recipes(self, label="DOCUMENTATION"):
        alts = []
        alt = models.Recipe.objects.filter(cause=models.Recipe.CAUSE_PULL_REQUEST_ALT)
        self.assertEqual(alt.count(), 1)
        alt = alt.first()
        alt.activate_label = "DOCUMENTATION"
        alt.save()
        alts.append(alt)
        return alts

class DBTester(TestCase, DBCompare):
    def setUp(self):
        self.client = Client()
        self.factory = RequestFactory()
