
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

import RecipeTester
from ci.tests import utils as test_utils
from ci import models
from mock import patch
from ci.github import api

class Tests(RecipeTester.RecipeTester):
    def create_default_build_user(self):
        self.server = test_utils.create_git_server(name="github.com")
        self.build_user = test_utils.create_user_with_token(name="moosebuild", server=self.server)

    def create_valid_recipes(self):
        self.create_recipe_in_repo("recipe_all.cfg", "all.cfg")
        self.create_recipe_in_repo("push_dep.cfg", "push_dep.cfg")
        self.create_recipe_in_repo("pr_dep.cfg", "pr_dep.cfg")
        self.create_recipe_in_repo("alt.cfg", "alt.cfg")
        self.create_default_build_user()

    def create_valid_with_check(self):
        # OK. New idaholab/moose/devel
        self.create_valid_recipes()
        self.set_counts()
        self.load_recipes()
        self.compare_counts(recipes=9, sha_changed=True, current=9, users=1, repos=1, branches=1, deps=4,
            num_push_recipes=2, num_manual_recipes=1, num_pr_recipes=2, num_pr_alt_recipes=2, num_push_alt_recipes=1,
            num_steps=15, num_step_envs=60, num_recipe_envs=15, num_prestep=18, num_release_recipes=1)

    def test_no_recipes(self):
        # no recipes, nothing to do
        self.set_counts()
        self.load_recipes()
        self.compare_counts(sha_changed=True)

    def test_no_user(self):
        # moosebuild user doesn't exist
        self.set_counts()
        self.create_recipe_in_repo("push_dep.cfg", "push_dep.cfg")
        self.load_recipes()
        self.compare_counts(recipes=2, current=2, sha_changed=True, users=2, repos=1, branches=1, num_push_recipes=1, num_pr_alt_recipes=1,
            num_steps=4, num_step_envs=16, num_recipe_envs=4, num_prestep=4)

    def test_load_ok(self):
        # OK
        self.create_recipe_in_repo("push_dep.cfg", "push_dep.cfg")
        self.create_default_build_user()
        self.set_counts()
        self.load_recipes()
        self.compare_counts(recipes=2, current=2, sha_changed=True, users=1, repos=1, branches=1, num_push_recipes=1, num_pr_alt_recipes=1,
            num_steps=4, num_step_envs=16, num_recipe_envs=4, num_prestep=4)

    def test_repo_changed(self):
        # OK
        self.create_recipe_in_repo("push_dep.cfg", "push_dep.cfg")
        self.create_default_build_user()
        self.set_counts()
        self.load_recipes()
        self.compare_counts(recipes=2, current=2, sha_changed=True, users=1, repos=1, branches=1, num_push_recipes=1, num_pr_alt_recipes=1, num_steps=4, num_step_envs=16, num_recipe_envs=4, num_prestep=4)

        # Now artificially change the repo SHA
        recipe_repo = models.RecipeRepository.load()
        recipe_repo.sha = "1234"
        recipe_repo.save()
        self.set_counts()
        self.load_recipes()
        self.compare_counts(sha_changed=True)

    def test_no_dep(self):
        # dependency file doesn't exist
        self.set_counts()
        self.create_recipe_in_repo("recipe_all.cfg", "all.cfg")
        with self.assertRaises(RecipeTester.RecipeRepoReader.InvalidRecipe):
            self.load_recipes()
        self.compare_counts()

    def test_dep_invalid(self):
        # dependency file isn't valid
        self.set_counts()
        self.create_recipe_in_repo("recipe_all.cfg", "all.cfg")
        self.create_recipe_in_repo("push_dep.cfg", "pr_dep.cfg")
        self.create_recipe_in_repo("pr_dep.cfg", "push_dep.cfg")
        with self.assertRaises(RecipeTester.RecipeRepoReader.InvalidDependency):
            self.load_recipes()
        self.compare_counts()

    def test_load_deps_ok(self):
        # OK. New idaholab/moose/devel
        self.create_valid_with_check()

    def test_no_change(self):
        # Start off with valid recipes
        self.create_valid_with_check()

        # OK, repo sha hasn't changed so no changes.
        self.set_counts()
        self.load_recipes()
        self.compare_counts()

    def test_recipe_changed(self):
        # start with valid recipes
        self.create_valid_with_check()

        # a recipe changed, should have a new recipe but since
        # none of the recipes have jobs attached, the old ones
        # will get deleted and get recreated.
        pr_recipe = self.find_recipe_dict("recipes/pr_dep.cfg")
        pr_recipe["priority_pull_request"] = 100
        self.write_recipe_to_repo(pr_recipe, "pr_dep.cfg")
        self.set_counts()
        self.load_recipes()
        self.compare_counts(sha_changed=True)

    def test_changed_recipe_with_jobs(self):
        # start with valid recipes
        self.create_valid_with_check()

        # change a recipe but now the old ones have jobs attached.
        # so 1 new recipe should be added
        for r in models.Recipe.objects.all():
            test_utils.create_job(recipe=r, user=self.build_user)

        pr_recipe = self.find_recipe_dict("recipes/pr_dep.cfg")
        pr_recipe["priority_pull_request"] = 99
        self.write_recipe_to_repo(pr_recipe, "pr_dep.cfg")
        self.set_counts()
        self.load_recipes()
        self.compare_counts(sha_changed=True, recipes=1, num_pr_recipes=1, num_steps=1, num_step_envs=4, num_recipe_envs=1, num_prestep=2)
        q = models.Recipe.objects.filter(filename=pr_recipe["filename"])
        self.assertEqual(q.count(), 2)
        q = q.filter(current=True)
        self.assertEqual(q.count(), 1)
        new_r = q.first()
        q = models.Recipe.objects.filter(filename=new_r.filename).exclude(pk=new_r.pk)
        self.assertEqual(q.count(), 1)
        old_r = q.first()
        self.assertNotEqual(old_r.filename_sha, new_r.filename_sha)

    def test_pr_alt_deps(self):
        self.create_default_build_user()
        self.create_recipe_in_repo("push.cfg", "push.cfg")
        self.set_counts()
        # push depends on push_dep.cfg
        # alt_pr depends on pr_dep.cfg
        with self.assertRaises(RecipeTester.RecipeRepoReader.InvalidRecipe):
            self.load_recipes()
        self.compare_counts()

        self.create_recipe_in_repo("push_dep.cfg", "push_dep.cfg")
        self.create_recipe_in_repo("push_dep.cfg", "pr_dep.cfg")
        self.set_counts()
        with self.assertRaises(RecipeTester.RecipeRepoReader.InvalidDependency):
            self.load_recipes()
        self.compare_counts()

        self.create_recipe_in_repo("pr_dep.cfg", "pr_dep.cfg")
        self.load_recipes()
        self.compare_counts(recipes=5, sha_changed=True, current=5, users=1, repos=1, branches=1, deps=2, num_push_recipes=2, num_pr_recipes=1, num_pr_alt_recipes=2,
            num_steps=9, num_step_envs=36, num_recipe_envs=9, num_prestep=10)

    def test_update_pull_requests(self):
        self.create_valid_with_check()
        self.set_counts()
        self.creator.update_pull_requests()
        self.compare_counts()
        # update_pull_requests doesn't depend on recipes in the filesystem
        pr = test_utils.create_pr()
        self.assertEqual(self.build_user.recipes.filter(cause=models.Recipe.CAUSE_PULL_REQUEST_ALT).count(), 2)
        r1_orig = self.build_user.recipes.filter(cause=models.Recipe.CAUSE_PULL_REQUEST_ALT).first()
        r1 = test_utils.create_recipe(name="alt_pr", user=r1_orig.build_user, repo=r1_orig.repository, cause=r1_orig.cause)
        r1.filename = r1_orig.filename
        r1.save()
        r1_orig.current = False
        r1_orig.save()
        self.assertEqual(pr.alternate_recipes.count(), 0)
        pr.alternate_recipes.add(r1_orig)
        self.set_counts()
        self.creator.update_pull_requests()
        self.compare_counts()
        self.assertEqual(pr.alternate_recipes.first().pk, r1.pk)

    def test_different_allows(self):
        # test different combination of allow_on_pr and allow_on_push
        self.create_default_build_user()
        self.create_recipe_in_repo("alt.cfg", "alt.cfg")
        self.set_counts()
        # alt depends on pr_dep.cfg, push_def.cfg
        with self.assertRaises(RecipeTester.RecipeRepoReader.InvalidRecipe):
            self.load_recipes()
        self.compare_counts()

        self.create_recipe_in_repo("push_dep.cfg", "push_dep.cfg")
        self.create_recipe_in_repo("push_dep.cfg", "pr_dep.cfg")
        self.set_counts()
        with self.assertRaises(RecipeTester.RecipeRepoReader.InvalidDependency):
            self.load_recipes()
        self.compare_counts()

        self.create_recipe_in_repo("pr_dep.cfg", "pr_dep.cfg")
        self.load_recipes()
        self.compare_counts(recipes=5, sha_changed=True, current=5, users=1, repos=1, branches=1, deps=2, num_push_recipes=1, num_pr_alt_recipes=2,
            num_pr_recipes=1, num_steps=7, num_step_envs=28, num_recipe_envs=7, num_prestep=10, num_push_alt_recipes=1)

    def test_deactivate(self):
        # start with valid recipes
        self.create_recipe_in_repo("pr.cfg", "pr.cfg")
        self.create_recipe_in_repo("pr_dep.cfg", "pr_dep.cfg")
        self.set_counts()
        self.create_default_build_user()
        self.load_recipes()
        self.compare_counts(recipes=2, sha_changed=True, current=2, users=2, repos=1, deps=1,
            num_pr_recipes=2, num_steps=2, num_step_envs=8, num_recipe_envs=2, num_prestep=4)

        pr_recipe = self.find_recipe_dict("recipes/pr_dep.cfg")
        pr_recipe["active"] = False
        self.write_recipe_to_repo(pr_recipe, "pr_dep.cfg")
        # The dependency is not active so other ones depend on a bad recipe
        self.set_counts()
        with self.assertRaises(RecipeTester.RecipeRepoReader.InvalidDependency):
            self.load_recipes()
        self.compare_counts()
        pr_recipe["active"] = True
        self.write_recipe_to_repo(pr_recipe, "pr_dep.cfg")

        # let them have jobs
        for r in models.Recipe.objects.all():
            test_utils.create_job(recipe=r, user=self.build_user)

        pr_recipe = self.find_recipe_dict("recipes/pr.cfg")
        pr_recipe["active"] = False
        self.write_recipe_to_repo(pr_recipe, "pr.cfg")
        self.set_counts()
        self.load_recipes()
        self.compare_counts(sha_changed=True, recipes=2, deps=1, num_pr_recipes=2, num_steps=2, num_step_envs=8, num_recipe_envs=2, num_prestep=4)
        q = models.Recipe.objects.filter(current=True)
        self.assertEqual(q.count(), 2)
        self.assertEqual(q.filter(active=True).count(), 1)

        # make sure it stays deactivated
        pr_recipe["display_name"] = "Other name"
        self.write_recipe_to_repo(pr_recipe, "pr.cfg")
        self.set_counts()
        self.load_recipes()
        self.compare_counts(sha_changed=True)
        q = models.Recipe.objects.filter(current=True)
        self.assertEqual(q.count(), 2)
        self.assertEqual(q.filter(active=True).count(), 1)

        # activate it again
        pr_recipe["active"] = True
        self.write_recipe_to_repo(pr_recipe, "pr.cfg")
        self.set_counts()
        self.load_recipes()
        self.compare_counts(sha_changed=True)
        q = models.Recipe.objects.filter(current=True)
        self.assertEqual(q.count(), 2)
        self.assertEqual(q.filter(active=True).count(), 2)

    @patch.object(api.GitHubAPI, 'install_webhooks')
    def test_install_webhooks(self, mock_install):
        mock_install.side_effect = Exception("Bam!")
        self.create_valid_recipes()
        self.load_recipes()
