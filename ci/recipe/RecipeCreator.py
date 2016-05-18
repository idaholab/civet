from django.conf import settings
from django.db import transaction
import RecipeRepoReader
import file_utils
import utils
from ci import models

class RecipeCreator(object):
  """
  Takes a list of recipe dicts and creates records in the database.
  """
  def __init__(self, repo_dir):
    super(RecipeCreator, self).__init__()
    self.repo_dir = repo_dir

  @transaction.atomic
  def load_recipes(self):
    recipe_repo_rec = models.RecipeRepository.load()
    repo_sha = file_utils.get_repo_sha(self.repo_dir)
    if repo_sha == recipe_repo_rec.sha:
      print("Repo the same, not creating recipes: %s" % repo_sha)
      return

    models.Recipe.objects.filter(jobs__isnull=True).delete()
    for recipe in models.Recipe.objects.filter(current=True).all():
      recipe.current = False
      recipe.save()
    repo_reader = RecipeRepoReader.RecipeRepoReader(self.repo_dir)
    sorted_recipes = {}
    for recipe in repo_reader.recipes:
      if not recipe["active"]:
        continue
      data = utils.parse_repo(recipe["repository"])
      server_dict = sorted_recipes.get(data[0], {})
      user_dict = server_dict.get(recipe["build_user"], {})
      owner_dict = user_dict.get(data[1], {})
      repo_list = owner_dict.get(data[2], [])
      repo_list.append(recipe)
      owner_dict[data[2]] = repo_list
      user_dict[data[1]] = owner_dict
      server_dict[recipe["build_user"]] = user_dict
      sorted_recipes[data[0]] = server_dict

    for server in settings.INSTALLED_GITSERVERS:
      server_rec = models.GitServer.objects.get(host_type=server)
      print("Loading recipes for %s" % server_rec)
      for build_user, owners_dict in sorted_recipes.get(server_rec.name, {}).iteritems():
        try:
          build_user_rec = models.GitUser.objects.get(name=build_user, server=server_rec)
        except models.GitUser.DoesNotExist:
          err_str = "Build user %s on %s does not exist in the database. They need to have signed in once." % (build_user, server_rec)
          print(err_str)
          raise RecipeRepoReader.InvalidRecipe(err_str)

        for owner, repo_dict in owners_dict.iteritems():
          owner_rec, created = models.GitUser.objects.get_or_create(name=owner, server=server_rec)
          for repo, recipes in repo_dict.iteritems():
            repo_rec, created = models.Repository.objects.get_or_create(name=repo, user=owner_rec)
            for recipe in recipes:
              if recipe["trigger_pull_request"]:
                self.create_recipe(recipe, build_user_rec, repo_rec, None, models.Recipe.CAUSE_PULL_REQUEST)
              if recipe["allow_on_pr"] and not recipe["trigger_pull_request"]:
                self.create_recipe(recipe, build_user_rec, repo_rec, None, models.Recipe.CAUSE_PULL_REQUEST_ALT)
              if recipe["trigger_push"] and recipe["trigger_push_branch"]:
                branch, created = models.Branch.objects.get_or_create(name=recipe["trigger_push_branch"], repository=repo_rec)
                self.create_recipe(recipe, build_user_rec, repo_rec, branch, models.Recipe.CAUSE_PUSH)
              if recipe["trigger_manual"] and recipe["trigger_manual_branch"]:
                branch, created = models.Branch.objects.get_or_create(name=recipe["trigger_manual_branch"], repository=repo_rec)
                self.create_recipe(recipe, build_user_rec, repo_rec, branch, models.Recipe.CAUSE_MANUAL)
            if (not self.set_dependencies(recipes, "pullrequest_dependencies", models.Recipe.CAUSE_PULL_REQUEST)
                or not self.set_dependencies(recipes, "pullrequest_dependencies", models.Recipe.CAUSE_PULL_REQUEST_ALT, dep_cause=models.Recipe.CAUSE_PULL_REQUEST)
                or not self.set_dependencies(recipes, "push_dependencies", models.Recipe.CAUSE_PUSH)
                or not self.set_dependencies(recipes, "manual_dependencies", models.Recipe.CAUSE_MANUAL) ):
              raise RecipeRepoReader.InvalidDependency("Invalid depenencies!")
    recipe_repo_rec.sha = repo_sha
    recipe_repo_rec.save()

  def create_recipe(self, recipe, build_user, repo, branch, cause):
    recipe_rec, created = models.Recipe.objects.get_or_create(
        filename=recipe["filename"],
        filename_sha=recipe["sha"],
        name=recipe["name"],
        display_name=recipe["display_name"],
        build_user=build_user,
        repository=repo,
        branch=branch,
        cause=cause,
        )
    recipe_rec.current = True
    recipe_rec.save()
    if created:
      self.set_recipe(recipe_rec, recipe, cause)
      print("Created new recipe %s: %s: %s: %s" % (recipe_rec.name, recipe_rec.filename, recipe_rec.filename_sha, recipe_rec.cause_str()))
    else:
      recipe_rec.dependencies.clear()
    return recipe_rec

  def set_dependencies(self, recipe_list, dep_key, cause, dep_cause=None):
    """
    Set the models.RecipeDependency records for a recipe.
    Input:
      recipe_obj: models.Recipe to set the dependencies for
      recipe_dict: list of recipe dicts to get the names of the dependencies.
      recipe_objs: List of models.Recipe records that correspond to recipe_dict. We can only search this list as they are the only valid dependencies.
      dep_key: str: Key in the dict to get the dependency list
    """
    ok = True
    if dep_cause == None:
      dep_cause = cause

    for r in recipe_list:
      recipe_rec = models.Recipe.objects.filter(filename=r["filename"], current=True, cause=cause).first()
      if not recipe_rec:
        continue
      for dep in r[dep_key]:
        try:
          dep_rec = models.Recipe.objects.filter(filename=dep, current=True, cause=dep_cause).first()
          recipe_dep, created = models.RecipeDependency.objects.get_or_create(recipe=recipe_rec, dependency=dep_rec)
          print("Recipe %s -> %s : %s" % (recipe_rec, dep_rec, recipe_rec.dependencies.count()))
        except Exception as e:
          print("Recipe: %s: Dependency not found: %s: %s" % (r["filename"], dep, e))
          ok = False
          break
    return ok

  def set_recipe(self, recipe, recipe_dict, cause):
    """
    Set various fields on the models.Recipe based on the recipe dict.
    Input:
      recipe: models.Recipe to set
      recipe_dict: dict of the recipe
      cause: models.Recipe.CAUSE*
    """
    recipe.name = recipe_dict["name"]
    recipe.display_name = recipe_dict["display_name"]
    recipe.filename = recipe_dict["filename"]
    recipe.filename_sha = recipe_dict["sha"]
    recipe.active = recipe_dict["active"]
    recipe.private = recipe_dict["private"]
    recipe.cause = cause

    if cause == models.Recipe.CAUSE_PULL_REQUEST:
      recipe.priority = recipe_dict["priority_pull_request"]
    elif cause == models.Recipe.CAUSE_MANUAL:
      recipe.priority = recipe_dict["priority_manual"]
    elif cause == models.Recipe.CAUSE_PUSH:
      recipe.priority = recipe_dict["priority_push"]

    autos = {"automatic": models.Recipe.FULL_AUTO, "manual": models.Recipe.MANUAL, "authorized": models.Recipe.AUTO_FOR_AUTHORIZED}
    recipe.automatic = autos[recipe_dict["automatic"]]

    for config in recipe_dict["build_configs"]:
      bc, created = models.BuildConfig.objects.get_or_create(name=config)
      recipe.build_configs.add(bc)
    recipe.save()
