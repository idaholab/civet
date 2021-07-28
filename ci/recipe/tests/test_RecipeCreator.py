
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
from ci.recipe.tests import RecipeTester
from ci.tests import utils as test_utils
from ci import models
from mock import patch
from django.test import override_settings
from ci.github import api
from ci.recipe import RecipeCreator

@override_settings(INSTALLED_GITSERVERS=[test_utils.github_config()])
class Tests(RecipeTester.RecipeTester):
    def create_valid_recipes(self, recipes_dir):
        self.create_recipe_in_repo(recipes_dir, "recipe_all.cfg", "all.cfg")
        self.create_recipe_in_repo(recipes_dir, "push_dep.cfg", "push_dep.cfg")
        self.create_recipe_in_repo(recipes_dir, "pr_dep.cfg", "pr_dep.cfg")
        self.create_recipe_in_repo(recipes_dir, "alt.cfg", "alt.cfg")

    def create_valid_with_check(self, recipes_dir):
        # OK. New idaholab/moose/devel
        self.create_valid_recipes(recipes_dir)
        self.set_counts()
        creator = self.check_load_recipes(recipes_dir, new=4)
        self.compare_counts(recipes=8,
                sha_changed=True,
                current=8,
                users=2,
                repos=1,
                branches=1,
                deps=3,
                num_push_recipes=2,
                num_manual_recipes=1,
                num_pr_recipes=2,
                num_pr_alt_recipes=2,
                num_steps=14,
                num_step_envs=56,
                num_recipe_envs=14,
                num_prestep=16,
                num_release_recipes=1)
        return creator

    def check_load_recipes(self, recipes_dir, removed=0, new=0, changed=0):
        creator, l_removed, l_new, l_changed = self.load_recipes(recipes_dir)
        self.assertEqual(l_removed, removed)
        self.assertEqual(l_new, new)
        self.assertEqual(l_changed, changed)
        return creator

    def test_no_recipes(self):
        # no recipes, nothing to do
        test_utils.create_git_server()
        with test_utils.RecipeDir() as recipes_dir:
            self.set_counts()
            self.check_load_recipes(recipes_dir)
            self.compare_counts(sha_changed=True)

    def test_no_user(self):
        # moosebuild user doesn't exist
        test_utils.create_git_server()
        with test_utils.RecipeDir() as recipes_dir:
            self.set_counts()
            self.create_recipe_in_repo(recipes_dir, "push_dep.cfg", "push_dep.cfg")
            self.check_load_recipes(recipes_dir, new=1)
            self.compare_counts(recipes=2,
                    current=2,
                    sha_changed=True,
                    users=2,
                    repos=1,
                    branches=1,
                    num_push_recipes=1,
                    num_pr_alt_recipes=1,
                    num_steps=4,
                    num_step_envs=16,
                    num_recipe_envs=4,
                    num_prestep=4)

    def test_load_ok(self):
        with test_utils.RecipeDir() as recipes_dir:
            # OK
            self.create_recipe_in_repo(recipes_dir, "push_dep.cfg", "push_dep.cfg")
            self.set_counts()
            self.check_load_recipes(recipes_dir, new=1)
            self.compare_counts(recipes=2,
                    current=2,
                    sha_changed=True,
                    users=2,
                    repos=1,
                    branches=1,
                    num_push_recipes=1,
                    num_pr_alt_recipes=1,
                    num_steps=4,
                    num_step_envs=16,
                    num_recipe_envs=4,
                    num_prestep=4)

    def test_repo_changed(self):
        with test_utils.RecipeDir() as recipes_dir:
            # OK
            self.create_recipe_in_repo(recipes_dir, "push_dep.cfg", "push_dep.cfg")
            self.set_counts()
            self.check_load_recipes(recipes_dir, new=1)
            self.compare_counts(recipes=2,
                    current=2,
                    sha_changed=True,
                    users=2,
                    repos=1,
                    branches=1,
                    num_push_recipes=1,
                    num_pr_alt_recipes=1,
                    num_steps=4,
                    num_step_envs=16,
                    num_recipe_envs=4,
                    num_prestep=4)

            # Now artificially change the repo SHA
            recipe_repo = models.RecipeRepository.load()
            recipe_repo.sha = "1234"
            recipe_repo.save()
            self.set_counts()
            self.check_load_recipes(recipes_dir)
            self.compare_counts(sha_changed=True)

    def test_no_dep(self):
        with test_utils.RecipeDir() as recipes_dir:
            # dependency file doesn't exist
            self.set_counts()
            self.create_recipe_in_repo(recipes_dir, "recipe_all.cfg", "all.cfg")
            with self.assertRaises(RecipeTester.RecipeRepoReader.InvalidRecipe):
                self.check_load_recipes(recipes_dir)
            self.compare_counts()

    def test_dep_invalid(self):
        with test_utils.RecipeDir() as recipes_dir:
            # dependency file isn't valid
            self.set_counts()
            self.create_recipe_in_repo(recipes_dir, "recipe_all.cfg", "all.cfg")
            self.create_recipe_in_repo(recipes_dir, "push_dep.cfg", "pr_dep.cfg")
            self.create_recipe_in_repo(recipes_dir, "pr_dep.cfg", "push_dep.cfg")
            with self.assertRaises(RecipeTester.RecipeRepoReader.InvalidDependency):
                self.check_load_recipes(recipes_dir)
            self.compare_counts()

    def test_load_deps_ok(self):
        with test_utils.RecipeDir() as recipes_dir:
            # OK. New idaholab/moose/devel
            self.create_valid_with_check(recipes_dir)
            r = models.Recipe.objects.filter(auto_cancel_on_push=True)
            self.assertEqual(r.count(), 1)
            r = models.Recipe.objects.filter(create_issue_on_fail=True)
            self.assertEqual(r.count(), 3) # push, release, manual

    def test_no_change(self):
        with test_utils.RecipeDir() as recipes_dir:
            # Start off with valid recipes
            self.create_valid_with_check(recipes_dir)

            # OK, repo sha hasn't changed so no changes.
            self.set_counts()
            self.check_load_recipes(recipes_dir)
            self.compare_counts()

    def test_recipe_changed(self):
        with test_utils.RecipeDir() as recipes_dir:
            # start with valid recipes
            self.create_valid_with_check(recipes_dir)

            # a recipe changed, should have a new recipe but since
            # none of the recipes have jobs attached, the old ones
            # will get deleted and get recreated.
            pr_recipe = self.find_recipe_dict("recipes/pr_dep.cfg")
            pr_recipe["priority_pull_request"] = 100
            self.write_recipe_to_repo(recipes_dir, pr_recipe, "pr_dep.cfg")
            self.set_counts()
            self.check_load_recipes(recipes_dir, changed=1)
            self.compare_counts(sha_changed=True)
            self.assertEqual(models.Recipe.objects.get(filename="recipes/pr_dep.cfg").priority, 100)

    def test_changed_recipe_with_jobs(self):
        with test_utils.RecipeDir() as recipes_dir:
            # start with valid recipes
            self.create_valid_with_check(recipes_dir)

            build_user = models.GitUser.objects.get(name="moosebuild")
            # change a recipe but now the old ones have jobs attached.
            # so 1 new recipe should be added
            for r in models.Recipe.objects.all():
                test_utils.create_job(recipe=r, user=build_user)

            pr_recipe = self.find_recipe_dict("recipes/pr_dep.cfg")
            pr_recipe["priority_pull_request"] = 99
            self.write_recipe_to_repo(recipes_dir, pr_recipe, "pr_dep.cfg")
            self.set_counts()
            self.check_load_recipes(recipes_dir, changed=1)
            self.compare_counts(sha_changed=True,
                    recipes=1,
                    num_pr_recipes=1,
                    num_steps=1,
                    num_step_envs=4,
                    num_recipe_envs=1,
                    num_prestep=2)

            q = models.Recipe.objects.filter(filename=pr_recipe["filename"])
            self.assertEqual(q.count(), 2)
            q = q.filter(current=True)
            self.assertEqual(q.count(), 1)
            new_r = q.first()
            q = models.Recipe.objects.filter(filename=new_r.filename).exclude(pk=new_r.pk)
            self.assertEqual(q.count(), 1)
            old_r = q.first()
            self.assertNotEqual(old_r.filename_sha, new_r.filename_sha)
            self.assertEqual(models.Recipe.objects.filter(depends_on__in=[old_r.pk]).count(), 0)
            self.assertEqual(models.Recipe.objects.filter(depends_on__in=[new_r.pk]).count(), 2)

    def test_pr_alt_deps(self):
        with test_utils.RecipeDir() as recipes_dir:
            self.create_recipe_in_repo(recipes_dir, "push.cfg", "push.cfg")
            self.set_counts()
            # push depends on push_dep.cfg
            # alt_pr depends on pr_dep.cfg
            with self.assertRaises(RecipeTester.RecipeRepoReader.InvalidRecipe):
                self.check_load_recipes(recipes_dir)
            self.compare_counts()

            self.create_recipe_in_repo(recipes_dir, "push_dep.cfg", "push_dep.cfg")
            self.create_recipe_in_repo(recipes_dir, "push_dep.cfg", "pr_dep.cfg")
            self.set_counts()
            with self.assertRaises(RecipeTester.RecipeRepoReader.InvalidDependency):
                self.check_load_recipes(recipes_dir)
            self.compare_counts()

            self.create_recipe_in_repo(recipes_dir, "pr_dep.cfg", "pr_dep.cfg")
            self.check_load_recipes(recipes_dir, new=3)
            self.compare_counts(recipes=5,
                    sha_changed=True,
                    current=5,
                    users=2,
                    repos=1,
                    branches=1,
                    deps=2,
                    num_push_recipes=2,
                    num_pr_recipes=1,
                    num_pr_alt_recipes=2,
                    num_steps=9,
                    num_step_envs=36,
                    num_recipe_envs=9,
                    num_prestep=10)

    def test_update_pull_requests(self):
        with test_utils.RecipeDir() as recipes_dir:
            creator = self.create_valid_with_check(recipes_dir)
            self.set_counts()
            creator._update_pull_requests()
            self.compare_counts()
            # update_pull_requests doesn't depend on recipes in the filesystem
            build_user = models.GitUser.objects.get(name="moosebuild")
            pr = test_utils.create_pr()
            self.assertEqual(build_user.recipes.filter(cause=models.Recipe.CAUSE_PULL_REQUEST_ALT).count(), 2)
            r1_orig = build_user.recipes.filter(cause=models.Recipe.CAUSE_PULL_REQUEST_ALT).first()
            r1 = test_utils.create_recipe(name="alt_pr", user=r1_orig.build_user, repo=r1_orig.repository, cause=r1_orig.cause)
            r1.filename = r1_orig.filename
            r1.save()
            r1_orig.current = False
            r1_orig.save()
            self.assertEqual(pr.alternate_recipes.count(), 0)
            pr.alternate_recipes.add(r1_orig)
            # There is an old alt recipe on the PR, it should be removed and replaced with the new one
            self.set_counts()
            creator._update_pull_requests()
            self.compare_counts()
            self.assertEqual(pr.alternate_recipes.count(), 1)
            self.assertEqual(pr.alternate_recipes.first().pk, r1.pk)

            r1.current = False
            r1.save()
            self.set_counts()
            # Now there are not current alt PR recipes
            creator._update_pull_requests()
            self.compare_counts(num_pr_alts=-1)
            self.assertEqual(pr.alternate_recipes.count(), 0)

    def test_different_allows(self):
        with test_utils.RecipeDir() as recipes_dir:
            # test different combination of allow_on_pr
            self.create_recipe_in_repo(recipes_dir, "alt.cfg", "alt.cfg")
            self.set_counts()
            # alt depends on pr_dep.cfg
            with self.assertRaises(RecipeTester.RecipeRepoReader.InvalidRecipe):
                self.check_load_recipes(recipes_dir)
            self.compare_counts()

            self.create_recipe_in_repo(recipes_dir, "push_dep.cfg", "push_dep.cfg")
            self.create_recipe_in_repo(recipes_dir, "push_dep.cfg", "pr_dep.cfg")
            self.set_counts()
            with self.assertRaises(RecipeTester.RecipeRepoReader.InvalidDependency):
                self.check_load_recipes(recipes_dir)
            self.compare_counts()

            self.create_recipe_in_repo(recipes_dir, "pr_dep.cfg", "pr_dep.cfg")
            self.check_load_recipes(recipes_dir, new=3)
            self.compare_counts(recipes=4,
                    sha_changed=True,
                    current=4,
                    users=2,
                    repos=1,
                    branches=1,
                    deps=1,
                    num_push_recipes=1,
                    num_pr_alt_recipes=2,
                    num_pr_recipes=1,
                    num_steps=6,
                    num_step_envs=24,
                    num_recipe_envs=6,
                    num_prestep=8)

    def test_deactivate(self):
        with test_utils.RecipeDir() as recipes_dir:
            # start with valid recipes
            self.create_recipe_in_repo(recipes_dir, "pr.cfg", "pr.cfg")
            self.create_recipe_in_repo(recipes_dir, "pr_dep.cfg", "pr_dep.cfg")
            self.set_counts()
            self.check_load_recipes(recipes_dir, new=2)
            self.compare_counts(recipes=2,
                    sha_changed=True,
                    current=2,
                    users=2,
                    repos=1,
                    deps=1,
                    num_pr_recipes=2,
                    num_steps=2,
                    num_step_envs=8,
                    num_recipe_envs=2,
                    num_prestep=4)

            pr_recipe = self.find_recipe_dict("recipes/pr_dep.cfg")
            pr_recipe["active"] = False
            self.write_recipe_to_repo(recipes_dir, pr_recipe, "pr_dep.cfg")
            # The dependency is not active so other ones depend on a bad recipe
            self.set_counts()
            with self.assertRaises(RecipeTester.RecipeRepoReader.InvalidDependency):
                self.check_load_recipes(recipes_dir)
            self.compare_counts()
            pr_recipe["active"] = True
            self.write_recipe_to_repo(recipes_dir, pr_recipe, "pr_dep.cfg")
            build_user = models.GitUser.objects.get(name="moosebuild")

            # let them have jobs
            for r in models.Recipe.objects.all():
                test_utils.create_job(recipe=r, user=build_user)

            pr_recipe = self.find_recipe_dict("recipes/pr.cfg")
            pr_recipe["active"] = False
            self.write_recipe_to_repo(recipes_dir, pr_recipe, "pr.cfg")
            self.set_counts()
            self.check_load_recipes(recipes_dir, changed=2)
            self.compare_counts(sha_changed=True,
                    recipes=2,
                    deps=1,
                    num_pr_recipes=2,
                    num_steps=2,
                    num_step_envs=8,
                    num_recipe_envs=2,
                    num_prestep=4)
            q = models.Recipe.objects.filter(current=True)
            self.assertEqual(q.count(), 2)
            self.assertEqual(q.filter(active=True).count(), 1)

            # make sure it stays deactivated
            pr_recipe["display_name"] = "Other name"
            self.write_recipe_to_repo(recipes_dir, pr_recipe, "pr.cfg")
            self.set_counts()
            self.check_load_recipes(recipes_dir, changed=1)
            self.compare_counts(sha_changed=True)
            q = models.Recipe.objects.filter(current=True)
            self.assertEqual(q.count(), 2)
            self.assertEqual(q.filter(active=True).count(), 1)

            # activate it again
            pr_recipe["active"] = True
            self.write_recipe_to_repo(recipes_dir, pr_recipe, "pr.cfg")
            self.set_counts()
            self.check_load_recipes(recipes_dir, changed=1)
            self.compare_counts(sha_changed=True)
            q = models.Recipe.objects.filter(current=True)
            self.assertEqual(q.count(), 2)
            self.assertEqual(q.filter(active=True).count(), 2)

    @patch.object(api.GitHubAPI, 'install_webhooks')
    def test_install_webhooks(self, mock_install):
        mock_install.side_effect = Exception("Bam!")
        with test_utils.RecipeDir() as recipes_dir:
            self.create_valid_recipes(recipes_dir)
            creator = RecipeCreator.RecipeCreator(recipes_dir)
            creator.install_webhooks()
            self.assertEqual(mock_install.call_count, 0)
            with self.settings(INSTALLED_GITSERVERS=[test_utils.github_config(install_webhook=True)]):
                creator.install_webhooks()
                self.assertEqual(mock_install.call_count, 1)

    def test_private(self):
        test_utils.create_git_server()
        with test_utils.RecipeDir() as recipes_dir:
            self.create_recipe_in_repo(recipes_dir, "recipe_private.cfg", "private.cfg")
            self.set_counts()
            self.check_load_recipes(recipes_dir, new=1)
            self.compare_counts(sha_changed=True,
                    recipes=1,
                    num_pr_recipes=1,
                    num_steps=1,
                    num_step_envs=1,
                    current=1,
                    users=2,
                    repos=1,
                    viewable_teams=2)

    def test_removed(self):
        test_utils.create_git_server()
        with test_utils.RecipeDir() as recipes_dir:
            self.create_valid_with_check(recipes_dir)
            self.remove_recipe_from_repo(recipes_dir, "alt.cfg")
            self.set_counts()
            self.check_load_recipes(recipes_dir, removed=1)
            self.compare_counts(sha_changed=True,
                    recipes=-1,
                    deps=-1,
                    current=-1,
                    num_pr_alt_recipes=-1,
                    num_steps=-1,
                    num_step_envs=-4,
                    num_recipe_envs=-1,
                    num_prestep=-2,
                    )

            # change a recipe but now the old ones have jobs attached.
            # so 1 new recipe should be added
            build_user = models.GitUser.objects.get(name="moosebuild")
            for r in models.Recipe.objects.all():
                test_utils.create_job(recipe=r, user=build_user)

            self.remove_recipe_from_repo(recipes_dir, "all.cfg")
            self.set_counts()
            self.check_load_recipes(recipes_dir, removed=1)
            self.compare_counts(sha_changed=True, current=-4)

    def test_client_runner_user(self):
        with test_utils.RecipeDir() as recipes_dir:
            self.create_valid_with_check(recipes_dir)
            build_user = models.GitUser.objects.get(name="moosebuild")
            r = models.Recipe.objects.get(filename="recipes/pr_dep.cfg")
            self.assertEqual(r.client_runner_user, None)
            pr_recipe = self.find_recipe_dict("recipes/pr_dep.cfg")
            pr_recipe["client_runner_user"] = build_user.name
            self.write_recipe_to_repo(recipes_dir, pr_recipe, "pr_dep.cfg")
            self.set_counts()
            self.check_load_recipes(recipes_dir, changed=1)
            self.compare_counts(sha_changed=True)
            r = models.Recipe.objects.get(filename="recipes/pr_dep.cfg")
            self.assertEqual(r.client_runner_user, build_user)
