
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
from ci.recipe.RecipeReader import RecipeReader
from ci.recipe import RecipeWriter
from ci.tests import utils
from ci.recipe.tests import RecipeTester

class Tests(RecipeTester.RecipeTester):
    def test_write(self):
        with utils.RecipeDir() as recipe_dir:
            fname = self.create_recipe_in_repo(recipe_dir, "recipe_all.cfg", "recipe.cfg")
            self.create_recipe_in_repo(recipe_dir, "recipe_push.cfg", "push_dep.cfg")
            self.create_recipe_in_repo(recipe_dir, "recipe_pr.cfg", "pr_dep.cfg")
            self.write_script_to_repo(recipe_dir, "contents", "1.sh")
            self.write_script_to_repo(recipe_dir, "contents", "2.sh")
            reader = RecipeReader(recipe_dir, fname)
            r = reader.read()
            self.assertEqual(r.get("repository"), "git@dummy_git_server:idaholab/civet.git")
            r["repository"] = "new_repo"

            global_env = r.get("global_env")
            self.assertEqual(len(global_env), 2)
            r["global_env"]["APPLICATION_NAME"] = "new_app"

            global_sources = r.get("global_sources")
            self.assertEqual(len(global_sources), 2)
            r["global_sources"][0] = "new_source"

            deps = r.get("pullrequest_dependencies")
            self.assertEqual(len(deps), 1)
            r["pullrequest_dependencies"][0] = "new_dep"

            steps = r.get("steps")
            self.assertEqual(len(steps), 2)
            r["steps"][0]["name"] = "new_step"

            self.assertTrue(RecipeWriter.write_recipe_to_repo(recipe_dir, r, "new_file.cfg"))
            reader = RecipeReader(recipe_dir, "new_file.cfg")
            r = reader.read()
            # we changed the source and the dep so now the recipe doesn't pass the check.
            self.assertEqual(r, {})
            r = reader.read(do_check=False)
            self.assertEqual(r["repository"], "new_repo")
            self.assertEqual(r["global_env"]["APPLICATION_NAME"], "new_app")
            self.assertEqual(r["global_sources"][0], "new_source")
            self.assertEqual(r["pullrequest_dependencies"][0], "new_dep")
            self.assertEqual(r["steps"][0]["name"], "new_step")

            self.assertFalse(RecipeWriter.write_recipe_to_repo('/foo', r, '../bar'))
