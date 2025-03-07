
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
from ci.tests import utils as test_utils
from ci.tests import DBTester
import os, subprocess
from django.conf import settings
from ci.recipe import RecipeCreator
from ci.recipe import RecipeRepoReader, RecipeWriter

class RecipeTester(DBTester.DBTester):
    def load_recipes(self, recipes_dir):
        creator = RecipeCreator.RecipeCreator(recipes_dir)
        removed, new, changed = creator.load_recipes()
        return creator, removed, new, changed

    def write_recipe_to_repo(self, recipes_dir, recipe_dict, recipe_filename):
        new_recipe = RecipeWriter.write_recipe_to_string(recipe_dict)
        self.write_to_repo(recipes_dir, new_recipe, recipe_filename)

    def create_recipe_in_repo(self, recipes_dir, test_recipe, repo_recipe, hostname=None):
        recipe_file = self.get_recipe(test_recipe)
        if hostname:
            recipe_file = recipe_file.replace("github.com", hostname)
        return self.write_to_repo(recipes_dir, recipe_file, repo_recipe)

    def write_script_to_repo(self, recipes_dir, file_data, script_name):
        fname = os.path.join("scripts", script_name)
        full_fname = os.path.join(recipes_dir, fname)
        with open(full_fname, "w") as f:
            f.write(file_data)
        subprocess.check_output(["git", "add", fname], cwd=recipes_dir)
        subprocess.check_output(["git", "commit", "-m", "Added %s" % fname], cwd=recipes_dir)
        return fname

    def remove_recipe_from_repo(self, recipes_dir, script_name):
        fname = os.path.join("recipes", script_name)
        subprocess.check_output(["git", "rm", fname], cwd=recipes_dir)
        subprocess.check_output(["git", "commit", "-m", "Remove %s" % fname], cwd=recipes_dir)

    def write_to_repo(self, recipes_dir, file_data, repo_recipe):
        fname = os.path.join("recipes", repo_recipe)
        full_fname = os.path.join(recipes_dir, fname)
        with open(full_fname, "w") as f:
            f.write(file_data)
        subprocess.check_output(["git", "add", fname], cwd=recipes_dir)
        subprocess.check_output(["git", "commit", "-m", "Added %s" % repo_recipe], cwd=recipes_dir)
        return fname

    def get_recipe(self, fname):
        p = '{}/{}'.format(os.path.dirname(__file__), fname)
        with open(p, 'r') as f:
            contents = f.read()
            return contents

    def create_records(self, recipe, branch):
        info = {}
        info["owner"] = test_utils.create_user(name=recipe["repository_owner"])
        info["build_user"] = test_utils.create_user_with_token(name=recipe["build_user"])
        info["repository"] = test_utils.create_repo(user=info["owner"], name=recipe["repository_name"])
        info["branch"] = test_utils.create_branch(repo=info["repository"], name=branch)
        return info

    def create_default_recipes(self, recipes_dir, server_type=settings.GITSERVER_GITHUB):
        hostname = "github.com"
        if server_type == settings.GITSERVER_GITLAB:
            hostname = "gitlab.com"

        self.recipe_file = self.create_recipe_in_repo("recipe_all.cfg", "recipe.cfg", hostname=hostname)
        self.recipe_pr_file = self.create_recipe_in_repo("pr_dep.cfg", "pr_dep.cfg", hostname=hostname)
        self.recipe_push_file = self.create_recipe_in_repo("push_dep.cfg", "push_dep.cfg", hostname=hostname)
        self.server = test_utils.create_git_server(host_type=server_type)
        self.build_user = test_utils.create_user_with_token(name="moosebuild", server=self.server)
        self.owner = test_utils.create_user(name="idaholab", server=self.server)
        self.repo = test_utils.create_repo(name="civet", user=self.owner)
        self.branch = test_utils.create_branch(name="devel", repo=self.repo)
        return self.load_recipes(recipes_dir)

    def find_recipe_dict(self, filename):
        for r in self.get_recipe_dicts():
            if r["filename"] == filename:
                return r

    def get_recipe_dicts(self):
        reader = RecipeRepoReader.RecipeRepoReader(settings.RECIPE_BASE_DIR)
        return reader.recipes
