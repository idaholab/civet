from django.conf import settings
from django.db import transaction
import file_utils
from ci import models
import sys, os

class RecipeCreator(object):
  """
  Takes a list of recipe dicts and creates records in the database.
  """
  def __init__(self, repo_dir):
    super(RecipeCreator, self).__init__()
    self.repo_dir = repo_dir
    self.sorted_recipes = {}
    self.repo_reader = None
    self.InvalidDependency = None
    self.InvalidRecipe = None
    self.load_reader()
    self.sort_recipes()

  def load_reader(self):
    """
    Since we need to load the module from "<self.repo_dir>/pyrecipe" we
    copy over the Exceptions in the module to this object.
    """
    try:
      sys.path.insert(1, os.path.join(self.repo_dir, "pyrecipe"))
      import RecipeRepoReader
      self.repo_reader = RecipeRepoReader.RecipeRepoReader(self.repo_dir)
      self.InvalidDependency = RecipeRepoReader.InvalidDependency
      self.InvalidRecipe = RecipeRepoReader.InvalidRecipe
    except Exception as e:
      print("Failed to load RecipeRepoReader. Loading recipes disabled: %s" % e)
      raise e

  def sort_recipes(self):
    """
    Get the recipes that RecipeRepoReader has and sort them.
    """
    self.sorted_recipes = {}
    for recipe in self.repo_reader.recipes:
      if not recipe["active"]:
        continue
      server_dict = self.sorted_recipes.get(recipe["repository_server"], {})
      user_dict = server_dict.get(recipe["build_user"], {})
      owner_dict = user_dict.get(recipe["repository_owner"], {})
      repo_list = owner_dict.get(recipe["repository_name"], [])
      repo_list.append(recipe)
      owner_dict[recipe["repository_name"]] = repo_list
      user_dict[recipe["repository_owner"]] = owner_dict
      server_dict[recipe["build_user"]] = user_dict
      self.sorted_recipes[recipe["repository_server"]] = server_dict

  @transaction.atomic
  def load_recipes(self):
    """
    Goes through all the recipes on disk and creates recipes in the database.
    Since there are various checks that are done, this is an atomic operation
    so that we can roll back if something goes wrong.
    This will also try to install webhooks for the repositories in the recipes.
    Exceptions:
      RecipeRepoReader.InvalideRecipe for a bad recipe
      RecipeRepoReader.InvalideDependency if a recipe has a bad dependency
    """
    recipe_repo_rec = models.RecipeRepository.load()
    repo_sha = file_utils.get_repo_sha(self.repo_dir)
    if repo_sha == recipe_repo_rec.sha:
      print("Repo the same, not creating recipes: %s" % repo_sha)
      return

    models.Recipe.objects.filter(jobs__isnull=True).delete()
    for recipe in models.Recipe.objects.filter(current=True).all():
      recipe.current = False
      recipe.save()

    for server in settings.INSTALLED_GITSERVERS:
      server_rec = models.GitServer.objects.get(host_type=server)
      print("Loading recipes for %s" % server_rec)
      for build_user, owners_dict in self.sorted_recipes.get(server_rec.name, {}).iteritems():
        try:
          build_user_rec = models.GitUser.objects.get(name=build_user, server=server_rec)
        except models.GitUser.DoesNotExist:
          err_str = "Build user %s on %s does not exist in the database. They need to have signed in once." % (build_user, server_rec)
          print(err_str)
          raise self.InvalidRecipe(err_str)

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
              raise self.RecipeRepoReader.InvalidDependency("Invalid depenencies!")
    recipe_repo_rec.sha = repo_sha
    recipe_repo_rec.save()
    self.update_pull_requests()
    self.install_webhooks(self.sorted_recipes)

  def install_webhooks(self, sorted_recipes):
    """
    Updates the webhooks on all the repositories.
    Input:
      sorted_recipes: dict: created in load_recipes
    """
    for server in settings.INSTALLED_GITSERVERS:
      server_rec = models.GitServer.objects.get(host_type=server)
      for build_user, owners_dict in sorted_recipes.get(server_rec.name, {}).iteritems():
        build_user_rec = models.GitUser.objects.get(name=build_user, server=server_rec)
        for owner, repo_dict in owners_dict.iteritems():
          owner_rec, created = models.GitUser.objects.get_or_create(name=owner, server=server_rec)
          for repo, recipes in repo_dict.iteritems():
            repo_rec, created = models.Repository.objects.get_or_create(name=repo, user=owner_rec)
            auth = server_rec.auth()
            auth_session = auth.start_session_for_user(build_user_rec)
            api = server_rec.api()
            print("Installing webhook for %s" % repo_rec)
            try:
              api.install_webhooks(auth_session, build_user_rec, repo_rec)
            except:
              # We might not have direct access to install a webhook, which is fine
              # if the repo is owned by non INL
              print("FAILED to install webhook for %s" % repo_rec)

  def create_recipe(self, recipe, build_user, repo, branch, cause):
    """
    Creates the recipe in the database along with some of it many to many fields.
    We don't set the recipe dependency here because we need all recipes to be
    created first.
    Input:
      recipe: dict: As created by RecipeReader
      build_user: models.GitUser: Owner of the recipe
      repo: models.Repository: repository that the recipe is attached to
      branch: models.Branch: branch that the recipe is attached to or None if a PR
      cause: models.Recipe.CAUSE_* to specify the trigger for this recipe
    Return:
      models.Recipe that corresponds to the recipe dict
    """
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
    if not created:
      # Nothing has changed for the recipe but it may now depend on
      # a new recipe
      recipe_rec.depends_on.clear()
      print("Recipe %s: already exists" % recipe_rec)
      return recipe_rec

    self.set_recipe(recipe_rec, recipe, cause)
    print("Created new recipe %s: %s: %s: %s" % (recipe_rec.name, recipe_rec.filename, recipe_rec.filename_sha, recipe_rec.cause_str()))
    for step in recipe["steps"]:
      self.create_step(recipe_rec, step)
    self.create_recipe_env(recipe_rec, recipe)
    self.create_prestep(recipe_rec, recipe)
    return recipe_rec

  def create_step(self, recipe_rec, step_dict):
    """
    Create a step and its environment.
    Input:
      recipe_rec: models.Recipe: Recipe to attach step to.
      step_dict: dict: A step dictionary as produced by RecipeReader in recipe["steps"]
    Return:
      models.Step
    """
    step_rec, created = models.Step.objects.get_or_create(recipe=recipe_rec,
        name=step_dict["name"],
        filename=step_dict["script"],
        position=step_dict["position"],
        abort_on_failure=step_dict["abort_on_failure"],
        allowed_to_fail=step_dict["allowed_to_fail"],
        )
    if created:
      #print("Recipe: %s: Created step %s" % (recipe_rec, step_rec))
      for name, value in step_dict["environment"].iteritems():
        step_env, created = models.StepEnvironment.objects.get_or_create(step=step_rec, name=name, value=value)
        #print("Step: %s: Created env %s" % (step_rec, step_env))
    return step_rec

  def create_recipe_env(self, recipe_rec, recipe_dict):
    """
    Create the recipe environment.
    Input:
      recipe_rec: models.Recipe: Recipe to attach step to.
      recipe_dict: dict: A recipe dictionary as produced by RecipeReader
    """
    for name, value in recipe_dict["global_env"].iteritems():
      recipe_env, created = models.RecipeEnvironment.objects.get_or_create(recipe=recipe_rec, name=name, value=value)

  def create_prestep(self, recipe_rec, recipe_dict):
    """
    Create the recipe prestep sources.
    Input:
      recipe_rec: models.Recipe: Recipe to attach step to.
      recipe_dict: dict: A recipe dictionary as produced by RecipeReader
    """
    for source in recipe_dict["global_sources"]:
      recipe_source, created = models.PreStepSource.objects.get_or_create(recipe=recipe_rec, filename=source)

  def set_dependencies(self, recipe_list, dep_key, cause, dep_cause=None):
    """
    Set the models.Recipe.depends_on records for a recipe.
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
          recipe_rec.depends_on.add(dep_rec)
          print("Recipe %s -> %s : %s" % (recipe_rec, dep_rec, recipe_rec.depends_on.count()))
        except Exception as e:
          print("Recipe: %s: Dependency not found: %s: %s" % (r["filename"], dep, e))
          ok = False
          break
    return ok

  def update_pull_requests(self):
    """
    Update all PRs to use the latest version of alternate recipes.
    """
    for pr in models.PullRequest.objects.exclude(alternate_recipes=None).prefetch_related("alternate_recipes").all():
      new_alt = []
      for alt in pr.alternate_recipes.all():
        recipe_rec = models.Recipe.objects.filter(filename=alt.filename, current=True, cause=alt.cause).first()
        if recipe_rec:
          new_alt.append(recipe_rec)
      pr.alternate_recipes.clear()
      for r in new_alt:
        pr.alternate_recipes.add(r)

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
