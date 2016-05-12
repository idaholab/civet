import os, fnmatch
from django.conf import settings
from RecipeReader import RecipeReader

class InvalidDependency(Exception):
  pass
class InvalidRecipe(Exception):
  pass

class RecipeRepoReader(object):
  """
  Reads all the recipes in a repository
  """
  def __init__(self, repo_dir=settings.RECIPE_BASE_DIR):
    """
    Constructor.
    Input:
      repo_dir: str: Path to the recipe repo.
    """
    super(RecipeRepoReader, self).__init__()
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
      if not self.check_depend(recipe, all_recipes, "push_dependencies", "trigger_push", "trigger_push_branch"):
        ret = False
      if not self.check_depend(recipe, all_recipes, "manual_dependencies", "trigger_manual", "trigger_manual_branch"):
        ret = False
      if not self.check_depend(recipe, all_recipes, "pullrequest_dependencies", "trigger_pull_request", None):
        ret = False
    return ret

  def check_depend(self, recipe, all_recipes, dep_key, trigger_key, branch_key):
    ret = True
    for dep in recipe[dep_key]:
      for dep_recipe in all_recipes:
        if dep_recipe["filename"] == dep:
          branch_same = True
          if branch_key:
            branch_same = dep_recipe[branch_key] == recipe[branch_key]
          if (not branch_same
              or not dep_recipe["active"]
              or dep_recipe["build_user"] != recipe["build_user"]
              or dep_recipe["repository"] != recipe["repository"]
              or not dep_recipe[trigger_key]):
            print("Recipe: %s: has invalid %s : %s" % (recipe["filename"], dep_key, dep))
            ret = False
          break
    return ret
