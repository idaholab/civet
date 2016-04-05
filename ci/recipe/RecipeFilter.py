import os, fnmatch, re
from RecipeReader import RecipeReader

class RecipeFilter(object):
  """
  Filter a list of recipe dicts by type(push/scheduled/PR)
  """
  def __init__(self, repo_dir):
    super(RecipeFilter, self).__init__()
    self.repo_dir = repo_dir
    self.recipe_dir = os.path.join(repo_dir, "recipes")
    self.recipes = self.read_recipes()

  def get_recipe_files(self):
    recipes = []
    for root, dirnames, files in os.walk(self.recipe_dir):
      for filename in fnmatch.filter(files, "*.cfg"):
        path = os.path.join(root, filename)
        recipes.append(os.path.relpath(path, self.repo_dir))
    return recipes

  def read_recipes(self):
    all_recipes = []
    for recipe_file in self.get_recipe_files():
      reader = RecipeReader(self.repo_dir, recipe_file)
      recipe = reader.read()
      if recipe:
        all_recipes.append(recipe)
    return all_recipes

  def parse_repo(self, repo):
    r = re.match("git@(.+):(.+)/(.+)\.git", repo)
    if r:
      return r.group(1), r.group(2), r.group(3)

    r = re.match("git@(.+):(.+)/(.+)", repo)
    if r:
      return r.group(1), r.group(2), r.group(3)

    r = re.match("https://(.+)/(.+)/(.+).git", repo)
    if r:
      return r.group(1), r.group(2), r.group(3)

    r = re.match("https://(.+)/(.+)/(.+)", repo)
    if r:
      return r.group(1), r.group(2), r.group(3)

  def same_repo(self, repo0, repo1):
    server0, owner0, repo0 = self.parse_repo(repo0)
    server1, owner1, repo1 = self.parse_repo(repo1)
    return server0 == server1 and owner0 == owner1 and repo0 == repo1


  def find_push_recipes(self, user, repo, branch):
    matched = []
    for recipe in self.recipes:
      if recipe["active"] and recipe["trigger_push"] and recipe["trigger_push_branch"] == branch and recipe["build_user"] == user and self.same_repo(recipe["repository"], repo.url()):
        matched.append(recipe)
    return matched

  def find_pr_recipes(self, builduser, repo):
    matched = []
    for recipe in self.recipes:
      if recipe["active"] and recipe["trigger_pull_request"] and recipe["build_user"] == builduser.name and self.same_repo(recipe["repository"], repo.url()):
        matched.append(recipe)
    return matched

  def find_alt_pr_recipes(self, builduser, repo):
    matched = []
    for recipe in self.recipes:
      if recipe["active"] and not recipe["trigger_pull_request"] and recipe["build_user"] == builduser.name and self.same_repo(recipe["repository"], repo.url()) and recipe["allow_on_pr"]:
        matched.append(recipe)
    return matched

  def find_manual_recipes(self, builduser, owner, repo, branch):
    matched = []
    for recipe in self.recipes:
      if recipe["active"] and recipe["trigger_manual"] and recipe["trigger_manual_branch"] == branch and recipe["build_user"] == builduser and self.same_repo(recipe["repository"], repo.url()):
        matched.append(recipe)
    return matched

