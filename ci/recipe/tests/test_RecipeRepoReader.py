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
from ci.recipe import RecipeWriter, RecipeRepoReader
from ci.tests import utils
from ci.recipe.tests import RecipeTester


class Tests(RecipeTester.RecipeTester):
    def test_reader(self):
        with utils.RecipeDir() as recipes_dir:
            reader = RecipeRepoReader.RecipeRepoReader(recipes_dir)
            self.assertEqual(len(reader.recipes), 0)

            self.create_recipe_in_repo(recipes_dir, "recipe_all.cfg", "recipe.cfg")
            with self.assertRaises(RecipeRepoReader.InvalidRecipe):
                reader = RecipeRepoReader.RecipeRepoReader(recipes_dir)

            self.create_recipe_in_repo(recipes_dir, "recipe_pr.cfg", "dep1.cfg")
            with self.assertRaises(RecipeRepoReader.InvalidRecipe):
                reader = RecipeRepoReader.RecipeRepoReader(recipes_dir)

            self.write_script_to_repo(recipes_dir, "contents", "1.sh")
            self.write_script_to_repo(recipes_dir, "contents", "2.sh")

            self.create_recipe_in_repo(recipes_dir, "pr_dep.cfg", "pr_dep.cfg")
            self.create_recipe_in_repo(recipes_dir, "push_dep.cfg", "push_dep.cfg")
            reader = RecipeRepoReader.RecipeRepoReader(recipes_dir)
            self.assertEqual(len(reader.recipes), 4)

            self.create_recipe_in_repo(recipes_dir, "recipe_extra.cfg", "extra.cfg")
            reader = RecipeRepoReader.RecipeRepoReader(recipes_dir)
            self.assertEqual(len(reader.recipes), 5)

            for r in reader.recipes:
                if r["filename"] == "recipes/pr_dep.cfg":
                    r["build_user"] = "no_exist"
                    RecipeWriter.write_recipe_to_repo(recipes_dir, r, r["filename"])
                    break
            with self.assertRaises(RecipeRepoReader.InvalidDependency):
                reader = RecipeRepoReader.RecipeRepoReader(recipes_dir)

    def test_check_dependencies(self):
        with utils.RecipeDir() as recipes_dir:
            reader = RecipeRepoReader.RecipeRepoReader(recipes_dir)

            def create(filename, **kwargs):
                recipe = {
                    "filename": filename,
                    "active": True,
                    "build_user": "moosebuild",
                    "repository": "git@github.com:idaholab/civet",
                    "trigger_pull_request": True,
                    "trigger_push": True,
                    "trigger_push_branch": "devel",
                    "trigger_manual": True,
                    "trigger_manual_branch": "devel",
                    "pullrequest_dependencies": [],
                    "push_dependencies": [],
                    "manual_dependencies": [],
                }
                recipe.update(kwargs)
                return recipe

            dep = create("dep.cfg")
            recipe = create("recipe.cfg", manual_dependencies=["dep.cfg"])
            inactive = create("inactive.cfg", active=False, push_dependencies=["no"])
            self.assertTrue(reader.check_dependencies([dep, recipe, inactive]))

            # manual dependency on a different branch
            dep["trigger_manual_branch"] = "master"
            self.assertFalse(reader.check_dependencies([dep, recipe, inactive]))

            # manual dependency doesn't trigger on manual
            dep["trigger_manual_branch"] = "devel"
            dep["trigger_manual"] = False
            self.assertFalse(reader.check_dependencies([dep, recipe, inactive]))
