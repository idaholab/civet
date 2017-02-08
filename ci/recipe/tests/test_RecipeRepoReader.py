
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

from ci.recipe import RecipeWriter
from ci.recipe import RecipeRepoReader
import RecipeTester

class Tests(RecipeTester.RecipeTester):
    def test_reader(self):
        reader = RecipeRepoReader.RecipeRepoReader(self.recipes_dir)
        self.assertEqual(len(reader.recipes), 0)

        self.create_recipe_in_repo("recipe_all.cfg", "recipe.cfg")
        with self.assertRaises(RecipeRepoReader.InvalidRecipe):
            reader = RecipeRepoReader.RecipeRepoReader(self.recipes_dir)

        self.create_recipe_in_repo("recipe_pr.cfg", "dep1.cfg")
        with self.assertRaises(RecipeRepoReader.InvalidRecipe):
            reader = RecipeRepoReader.RecipeRepoReader(self.recipes_dir)

        self.write_script_to_repo("contents", "1.sh")
        self.write_script_to_repo("contents", "2.sh")

        self.create_recipe_in_repo("pr_dep.cfg", "pr_dep.cfg")
        self.create_recipe_in_repo("push_dep.cfg", "push_dep.cfg")
        reader = RecipeRepoReader.RecipeRepoReader(self.recipes_dir)
        self.assertEqual(len(reader.recipes), 4)

        self.create_recipe_in_repo("recipe_extra.cfg", "extra.cfg")
        reader = RecipeRepoReader.RecipeRepoReader(self.recipes_dir)
        self.assertEqual(len(reader.recipes), 5)

        for r in reader.recipes:
            if r["filename"] == "recipes/pr_dep.cfg":
                r["build_user"] = "no_exist"
                RecipeWriter.write_recipe_to_repo(self.recipes_dir, r, r["filename"])
                break
        with self.assertRaises(RecipeRepoReader.InvalidDependency):
            reader = RecipeRepoReader.RecipeRepoReader(self.recipes_dir)
