
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

from ci.recipe.RecipeReader import RecipeReader
import RecipeTester
from ci.tests import utils

class Tests(RecipeTester.RecipeTester):
    def test_read(self):
        with utils.RecipeDir() as recipes_dir:
            fname = self.create_recipe_in_repo(recipes_dir, "recipe_all.cfg", "recipe.cfg")
            self.create_recipe_in_repo(recipes_dir, "push_dep.cfg", "push_dep.cfg")
            self.create_recipe_in_repo(recipes_dir, "recipe_extra.cfg", "extra.cfg")
            reader = RecipeReader(recipes_dir, fname)
            # should fail since dependency is not there
            r = reader.read()
            self.assertEqual(reader.check(), False)
            self.assertEqual(r, {})

            self.create_recipe_in_repo(recipes_dir, "pr_dep.cfg", "pr_dep.cfg")

            r = reader.read()
            self.assertEqual(reader.check(), True)

            self.assertEqual(r.get("name"), "Recipe with everything")
            self.assertEqual(r.get("display_name"), "Recipe with everything")
            self.assertEqual(len(r.get("sha")), 40)
            self.assertEqual(len(r.get("repo_sha")), 40)
            self.assertEqual(r.get("repository"), "git@dummy_git_server:idaholab/civet.git")
            self.assertEqual(r.get("private"), False)
            self.assertEqual(r.get("active"), True)
            self.assertEqual(r.get("automatic"), "authorized")
            self.assertEqual(r.get("build_user"), "moosebuild")
            self.assertEqual(r.get("build_configs"), ["linux-gnu"])
            self.assertEqual(r.get("trigger_push"), True)
            self.assertEqual(r.get("trigger_push_branch"), "devel")
            self.assertEqual(r.get("priority_push"), 1)
            self.assertEqual(r.get("trigger_pull_request"), True)
            self.assertEqual(r.get("priority_pull_request"), 2)
            self.assertEqual(r.get("trigger_manual"), True)
            self.assertEqual(r.get("trigger_manual_branch"), "devel")
            self.assertEqual(r.get("priority_manual"), 3)
            self.assertEqual(r.get("allow_on_pr"), False)

            global_env = r.get("global_env")
            self.assertEqual(len(global_env.keys()), 2)
            self.assertEqual(global_env.get("APPLICATION_NAME"), "civet")
            self.assertEqual(global_env.get("MOOSE_DIR"), "BUILD_ROOT/moose")

            global_sources = r.get("global_sources")
            self.assertEqual(len(global_sources), 2)
            self.assertEqual(global_sources, ["scripts/1.sh", "scripts/2.sh"])

            pr_deps = r.get("pullrequest_dependencies")
            self.assertEqual(len(pr_deps), 1)
            self.assertEqual(pr_deps, ["recipes/pr_dep.cfg"])

            push_deps = r.get("push_dependencies")
            self.assertEqual(len(push_deps), 1)
            self.assertEqual(push_deps, ["recipes/push_dep.cfg"])

            manual_deps = r.get("manual_dependencies")
            self.assertEqual(len(manual_deps), 0)

            steps = r.get("steps")
            self.assertEqual(len(steps), 2)
            self.assertEqual(steps[0].get("name"), "Pre Test")
            self.assertEqual(steps[0].get("script"), "scripts/1.sh")
            self.assertEqual(steps[0].get("abort_on_failure"), True)
            self.assertEqual(steps[0].get("allowed_to_fail"), True)
            self.assertEqual(len(steps[0].get("environment").keys()), 4)
            self.assertEqual(steps[0].get("environment").get("FOO"), "bar")

            self.assertEqual(steps[1].get("name"), "Next Step")
            self.assertEqual(steps[1].get("script"), "scripts/2.sh")
            self.assertEqual(steps[1].get("abort_on_failure"), False)
            self.assertEqual(steps[1].get("allowed_to_fail"), False)
            self.assertEqual(len(steps[1].get("environment").keys()), 4)
            self.assertEqual(steps[1].get("environment").get("ENV"), "some string")

    def test_check(self):
        with utils.RecipeDir() as recipes_dir:
            fname = self.create_recipe_in_repo(recipes_dir, "recipe_all.cfg", "recipe.cfg")
            self.create_recipe_in_repo(recipes_dir, "pr_dep.cfg", "pr_dep.cfg")
            reader = RecipeReader(recipes_dir, fname)
            r = reader.read()
            # should fail since dependency is not there
            self.assertEqual(reader.check(), False)
            self.assertEqual(r, {})

            self.create_recipe_in_repo(recipes_dir, "push_dep.cfg", "push_dep.cfg")

            r = reader.read()
            self.assertEqual(reader.check(), True)
            self.assertNotEqual(r, {})

            good_recipe = reader.recipe.copy()
            reader.recipe["display_name"] = ""
            self.assertEqual(reader.check(), True)
            self.assertEqual(reader.recipe["display_name"], reader.recipe["name"])

            reader.recipe["automatic"] = "foo"
            self.assertEqual(reader.check(), False)

            reader.recipe = good_recipe.copy()
            reader.recipe["trigger_pull_request"] = False
            reader.recipe["trigger_push"] = False
            reader.recipe["trigger_manual"] = False
            reader.recipe["allow_on_pr"] = False
            reader.recipe["trigger_release"] = False
            self.assertEqual(reader.check(), False)

            reader.recipe = good_recipe.copy()
            reader.recipe["trigger_pull_request"] = True
            reader.recipe["allow_on_pr"] = True
            self.assertEqual(reader.check(), False)

            reader.recipe = good_recipe.copy()
            reader.recipe["trigger_push"] = True
            reader.recipe["trigger_push_branch"] = ""
            self.assertEqual(reader.check(), False)

            reader.recipe = good_recipe.copy()
            reader.recipe["trigger_manual"] = True
            reader.recipe["trigger_manual_branch"] = ""
            self.assertEqual(reader.check(), False)

            reader.recipe = good_recipe.copy()
            reader.recipe["sha"] = ""
            self.assertEqual(reader.check(), False)

            reader.recipe = good_recipe.copy()
            reader.recipe["repo_sha"] = ""
            self.assertEqual(reader.check(), False)

            reader.recipe = good_recipe.copy()
            reader.recipe["build_configs"] = []
            self.assertEqual(reader.check(), False)

            reader.recipe = good_recipe.copy()
            reader.recipe["repository_owner"] = ""
            self.assertEqual(reader.check(), False)

            reader.recipe = good_recipe.copy()
            reader.recipe["global_sources"] = ["not a file"]
            self.assertEqual(reader.check(), False)

            reader.recipe = good_recipe.copy()
            reader.recipe["pullrequest_dependencies"] = ["not a file"]
            self.assertEqual(reader.check(), False)
            reader.recipe["pullrequest_dependencies"] = [fname]
            self.assertEqual(reader.check(), False)

            reader.recipe = good_recipe.copy()
            reader.recipe["push_dependencies"] = ["not a file"]
            self.assertEqual(reader.check(), False)
            reader.recipe["push_dependencies"] = [fname]
            self.assertEqual(reader.check(), False)

            reader.recipe = good_recipe.copy()
            reader.recipe["manual_dependencies"] = ["not a file"]
            self.assertEqual(reader.check(), False)
            reader.recipe["manual_dependencies"] = [fname]
            self.assertEqual(reader.check(), False)

            reader.recipe = good_recipe.copy()
            reader.recipe["release_dependencies"] = ["not a file"]
            self.assertEqual(reader.check(), False)
            reader.recipe["release_dependencies"] = [fname]
            self.assertEqual(reader.check(), False)

            reader.recipe = good_recipe.copy()
            reader.recipe["steps"] = []
            self.assertEqual(reader.check(), False)

            reader.recipe = good_recipe.copy()
            reader.recipe["steps"][0]["script"] = "not a file"
            self.assertEqual(reader.check(), False)

    def test_read_private(self):
        with utils.RecipeDir() as recipes_dir:
            fname = self.create_recipe_in_repo(recipes_dir, "recipe_private.cfg", "private.cfg")
            reader = RecipeReader(recipes_dir, fname)
            r = reader.read()
            self.assertEqual(reader.check(), True)
            self.assertEqual(r["private"], True)
            self.assertEqual(r["viewable_by_teams"], ["idaholab/MOOSE TEAM", "idaholab/OTHER TEAM"])

    def check_repo(self, d):
        self.assertEqual(d[0], "github.com")
        self.assertEqual(d[1], "idaholab")
        self.assertEqual(d[2], "civet")

    def test_parse_repo(self):
        with utils.RecipeDir() as recipes_dir:
            fname = self.create_recipe_in_repo(recipes_dir, "recipe_private.cfg", "private.cfg")
            reader = RecipeReader(recipes_dir, fname)
            r = reader.read()
            self.assertEqual(reader.check(), True)
            self.assertEqual(r["repository_server"], "dummy_git_server")
            self.assertEqual(r["repository_owner"], "idaholab")
            self.assertEqual(r["repository_name"], "civet")
            d = reader.parse_repo("git@github.com:idaholab/civet")
            self.check_repo(d)
            d = reader.parse_repo("git@github.com:idaholab/civet.git")
            self.check_repo(d)
            d = reader.parse_repo("https://github.com/idaholab/civet.git")
            self.check_repo(d)
            d = reader.parse_repo("https://github.com/idaholab/civet")
            self.check_repo(d)
            d = reader.parse_repo("https://github.com:idaholab/civet")
            self.assertEqual(d, None)

    def test_misc(self):
        with utils.RecipeDir() as recipes_dir:
            fname = self.create_recipe_in_repo(recipes_dir, "recipe_private.cfg", "private.cfg")
            reader = RecipeReader(recipes_dir, fname)
            self.assertEqual(reader.get_option("does not exist", "foo", 1), 1)
            self.assertEqual(reader.get_option("Main", "automatic", 2), 2)

            self.assertTrue(reader.set_steps())
            reader.config.add_section("BadSection")
            self.assertFalse(reader.set_steps())
            self.assertEqual(reader.read(), {})

            reader.config.set("BadSection", "script", "scripts/2.sh")
            self.assertTrue(reader.set_steps())

            self.assertNotEqual(reader.read(), {})
            reader.config.set("Main", "name", "")
            self.assertEqual(reader.read(), {})
