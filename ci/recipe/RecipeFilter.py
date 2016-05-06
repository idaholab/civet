import os, fnmatch
from RecipeReader import RecipeReader
import utils

class DependencyException(Exception):
  pass

class RecipeFilter(object):
  """
  Filter a list of recipe dicts by type(push/scheduled/PR)
  """
  def __init__(self, repo_dir):
    """
    Constructor.
    Input:
      repo_dir: str: Path to the recipe repo.
    """
    super(RecipeFilter, self).__init__()
    self.repo_dir = repo_dir
    self.recipe_dir = os.path.join(repo_dir, "recipes")
    self.recipes = self.read_recipes()

  def get_recipe_files(self):
    """
    Searches the recipe repo for *.cfg files.
    This returns ALL recipe files found.
    Return:
      list[str]: Of paths to recipes
    """
    recipes = []
    for root, dirnames, files in os.walk(self.recipe_dir):
      for filename in fnmatch.filter(files, "*.cfg"):
        path = os.path.join(root, filename)
        recipes.append(os.path.relpath(path, self.repo_dir))
    return recipes

  def read_recipes(self):
    """
    Converts all the recipes found by get_recipe_files() and converts them into dicts
    Return:
      list of recipe dicts
    """
    all_recipes = []
    for recipe_file in self.get_recipe_files():
      reader = RecipeReader(self.repo_dir, recipe_file)
      recipe = reader.read()
      if recipe:
        all_recipes.append(recipe)
    return all_recipes

  def find_push_recipes(self, user, branch):
    """
    Gets a list of PUSH recipes.
    Input:
      user: models.GitUser build user
      repo: models.Repository of the recipe
      branch: models.Branch of the recipe
    Return:
      list of recipe dicts
    """
    matched = []
    for recipe in self.recipes:
      if (recipe["active"]
        and recipe["trigger_push"]
        and recipe["trigger_push_branch"] == branch.name
        and recipe["build_user"] == user.name
        and utils.same_repo(recipe["repository"], branch.repository.git_url())):
        matched.append(recipe)
    self.check_matched_dependencies(matched, "push_dependencies")
    return matched

  def find_pr_recipes(self, builduser, repo):
    """
    Gets a list of PR recipes.
    Input:
      builduser: models.GitUser build user
      repo: models.Repository of the recipe
    Return:
      list of recipe dicts
    """
    matched = []
    for recipe in self.recipes:
      if (recipe["active"]
          and recipe["trigger_pull_request"]
          and recipe["build_user"] == builduser.name
          and utils.same_repo(recipe["repository"], repo.git_url())):
        matched.append(recipe)
    self.check_matched_dependencies(matched, "pullrequest_dependencies")
    return matched

  def find_alt_pr_recipes(self, builduser, repo):
    """
    Gets a list of recipes that can be optionally activated on a PR
    Input:
      builduser: models.GitUser build user
      repo: models.Repository of the recipe
    Return:
      list of recipe dicts
    """
    matched = []
    for recipe in self.recipes:
      if (recipe["active"]
          and not recipe["trigger_pull_request"]
          and recipe["allow_on_pr"]
          and recipe["build_user"] == builduser.name
          and utils.same_repo(recipe["repository"], repo.git_url())):
        matched.append(recipe)
    return matched

  def find_manual_recipes(self, builduser, branch):
    """
    Gets a list of scheduled recipes.
    Input:
      builduser: models.GitUser build user
      repo: models.Repository of the recipe
      branch: models.Branch of the recipe
    Return:
      list of recipe dicts
    """
    matched = []
    for recipe in self.recipes:
      if (recipe["active"]
          and recipe["trigger_manual"]
          and recipe["trigger_manual_branch"] == branch.name
          and recipe["build_user"] == builduser.name
          and utils.same_repo(recipe["repository"], branch.repository.git_url())):
        matched.append(recipe)
    self.check_matched_dependencies(matched, "manual_dependencies")
    return matched

  def check_matched_dependencies(self, matched, key):
    """
    Makes sure that the dependencies in the recipes found are within the list.
    This prevents having dependencies in a recipe that will never be activated because
    they are triggered differently. Ex, a PR recipe that has a dependency on a Push recipe.
    Input:
      matched: list of recipe dicts
      key: str: Key of the dependency list
    Raises:
      DependencyError if all the depenencies aren't within matched
    """
    for r in matched:
      for dep in r[key]:
        found = False
        for r_dep in matched:
          if dep == r_dep["filename"]:
            found = True
            break
        if not found:
          err = "Dependency not found: %s -> %s" % (r["filename"], dep)
          print(err)
          raise DependencyException(err)

  def find_user_recipes(self, builduser):
    """
    Finds all recipes for a build user.
    Input:
      builduser: models.GitUser build user
    Return:
      list of recipe dicts
    """
    matched = []
    for recipe in self.recipes:
      if recipe["build_user"] == builduser.name:
        matched.append(recipe)
    return matched
