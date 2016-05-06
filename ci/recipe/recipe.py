from django.conf import settings
import RecipeFilter, RecipeCreator, RecipeReader
from ci import models

def get_pr_recipes(builduser, repo):
  """
  Finds and creates PR recipes for builduser on repo.
  Input:
    builduser: models.GitUser: The specified build user
    repo: models.Repository: Repository to look for recipes.
  Return:
    A list of models.Recipe
  """
  rfilter = RecipeFilter.RecipeFilter(settings.RECIPE_BASE_DIR)
  rcreator = RecipeCreator.RecipeCreator()
  recipes = rfilter.find_pr_recipes(builduser, repo)
  return rcreator.pull_requests(recipes, builduser, repo)

def get_manual_recipes(builduser, branch):
  """
  Finds and creates manual recipes for builduser on branch.
  Input:
    builduser: models.GitUser: The specified build user
    branch: models.Branch: Branch to look for recipes.
  Return:
    A list of models.Recipe
  """
  rfilter = RecipeFilter.RecipeFilter(settings.RECIPE_BASE_DIR)
  rcreator = RecipeCreator.RecipeCreator()
  recipes = rfilter.find_manual_recipes(builduser, branch)
  return rcreator.manual(recipes, builduser, branch)

def get_push_recipes(builduser, branch):
  """
  Finds and creates manual recipes for builduser on branch.
  Input:
    builduser: models.GitUser: The specified build user
    branch: models.Branch: Branch to look for recipes.
  Return:
    A list of models.Recipe
  """
  rfilter = RecipeFilter.RecipeFilter(settings.RECIPE_BASE_DIR)
  rcreator = RecipeCreator.RecipeCreator()
  recipes = rfilter.find_push_recipes(builduser, branch)
  return rcreator.push(recipes, builduser, branch)

def update_recipe(recipe):
  """
  Given the information in the passed in recipe, check the repo for a newer version, based on filename.
  If there isn't a newer version (or the recipe isn't in the repo anymore) the same recipe is returned.
  Input:
    recipe: models.Recipe: Recipe to update
  Return
    models.Recipe
  """
  try:
    reader = RecipeReader.RecipeReader(settings.RECIPE_BASE_DIR, recipe.filename)
    new_recipe_dict = reader.read()
    if new_recipe_dict and new_recipe_dict["filename_sha"] != recipe.filename_sha:
      tmp_list = [new_recipe_dict]
      rcreator = RecipeCreator.RecipeCreator()
      new_recipe_list = [recipe]
      if recipe.cause == models.Recipe.CAUSE_MANUAL:
        new_recipe_list = rcreator.manual(tmp_list, recipe.build_user, recipe.branch)
      elif recipe.cause == models.Recipe.CAUSE_PULL_REQUEST:
        new_recipe_list = rcreator.pull_requests(tmp_list, recipe.build_user, recipe.repository)
      elif recipe.cause == models.Recipe.CAUSE_PUSH:
        new_recipe_list = rcreator.push(tmp_list, recipe.build_user, recipe.branch)
      return new_recipe_list
    else:
      return recipe
  except Exception:
    return recipe
