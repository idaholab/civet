#!/usr/bin/env python

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

import os, fnmatch
from RecipeReader import RecipeReader

class InvalidDependency(Exception):
  pass
class InvalidRecipe(Exception):
  pass

class RecipeRepoReader(object):
  """
  Reads all the recipes in a repository
  """
  def __init__(self, recipe_dir):
    """
    Constructor.
    Input:
      recipe_dir: str: Path to the recipe repo.
    """
    super(RecipeRepoReader, self).__init__()
    self.recipe_dir = recipe_dir
    self.recipes = self.read_recipes()

  def get_recipe_files(self):
    """
    Searches the recipe repo for *.cfg files.
    This returns ALL recipe files found.
    Return:
      list[str]: Of paths to recipes
    """
    recipes = []
    recipes_dir = os.path.join(self.recipe_dir, "recipes")
    for root, dirnames, files in os.walk(recipes_dir):
      for filename in fnmatch.filter(files, "*.cfg"):
        path = os.path.join(root, filename)
        recipes.append(os.path.relpath(path, self.recipe_dir))
    return recipes

  def read_recipes(self):
    """
    Converts all the recipes found by get_recipe_files() and converts them into dicts
    Return:
      list of recipe dicts
    """
    all_recipes = []
    for recipe_file in self.get_recipe_files():
      reader = RecipeReader(self.recipe_dir, recipe_file)
      recipe = reader.read()
      if recipe:
          all_recipes.append(recipe)
      else:
        raise InvalidRecipe(recipe_file)
    if not self.check_dependencies(all_recipes):
      raise InvalidDependency("Invalid dependencies!")
    return all_recipes

  def check_dependencies(self, all_recipes):
    ret = True
    for recipe in all_recipes:
      # the reader already checks for file existence.
      # We need to check for the same build user, repo and event type
      if not recipe["active"]:
        continue
      if not self.check_depend(recipe, all_recipes, "push_dependencies", "trigger_push", "trigger_push_branch", "allow_on_push"):
        ret = False
      if not self.check_depend(recipe, all_recipes, "manual_dependencies", "trigger_manual", "trigger_manual_branch"):
        ret = False
      if not self.check_depend(recipe, all_recipes, "pullrequest_dependencies", "trigger_pull_request", None):
        ret = False
    return ret

  def check_depend(self, recipe, all_recipes, dep_key, trigger_key, branch_key, alt_branch=None):
    ret = True
    for dep in recipe[dep_key]:
      for dep_recipe in all_recipes:
        if dep_recipe["filename"] == dep:
          branch_same = True
          if branch_key:
            branch_same = dep_recipe[branch_key] == recipe[branch_key]
            if not branch_same and alt_branch and recipe[alt_branch]:
              branch_same = dep_recipe[branch_key] == recipe[alt_branch]
          if (not branch_same
              or not dep_recipe["active"]
              or dep_recipe["build_user"] != recipe["build_user"]
              or dep_recipe["repository"] != recipe["repository"]
              or not dep_recipe[trigger_key]):
            print("Recipe: %s: has invalid %s : %s" % (recipe["filename"], dep_key, dep))
            ret = False
          break
    return ret

if __name__ == "__main__":
#  import json
  dirname = os.path.dirname(os.path.realpath(__file__))
  parent_dir = os.path.dirname(dirname)
  try:
    reader = RecipeRepoReader(parent_dir)
    #print(json.dumps(reader.recipes, indent=2))
  except Exception as e:
    print("Recipe repo is not valid: %s" % e)
