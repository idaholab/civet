from ci import models

class RecipeCreator(object):
  """
  Takes a list of recipe dicts and creates records in the database.
  """
  def __init__(self):
    super(RecipeCreator, self).__init__()

  def pull_requests(self, recipes, builduser, repo):
    """
    Read PR recipes from the repo and get or create the DB models.Recipe records.
    Input:
      recipes: list of recipe dicts as created by RecipeReader
      builduser: models.GitUser whos build key is attached to the recipe.
      repo: models.Repository where the PR is against
    Return:
      list of models.Recipe records corresponding to the input recipes
    """
    return self.create_recipes(recipes, builduser, repo, None, models.Recipe.CAUSE_PULL_REQUEST)

  def manual(self, recipes, builduser, branch):
    """
    Read scheduled recipes from the repo and get or create the DB models.Recipe records.
    Input:
      recipes: list of recipe dicts as created by RecipeReader
      builduser: models.GitUser whos build key is attached to the recipe.
      owner: models.GitUser of the branch owner
      repo: models.Repository of the branch
      branch: models.Branch where this recipe will act against
    Return:
      list of models.Recipe records corresponding to the input recipes
    """
    return self.create_recipes(recipes, builduser, branch.repository, branch, models.Recipe.CAUSE_MANUAL)

  def push(self, recipes, builduser, branch):
    """
    Read push recipes from the repo and get or create the DB models.Recipe records.
    Input:
      recipes: list of recipe dicts as created by RecipeReader
      builduser: models.GitUser whos build key is attached to the recipe.
      owner: models.GitUser of the branch owner
      repo: models.Repository of the branch
      branch: models.Branch where this recipe will act against
    Return:
      list of models.Recipe records corresponding to the input recipes
    """
    return self.create_recipes(recipes, builduser, branch.repository, branch, models.Recipe.CAUSE_PUSH)

  def create_recipes(self, recipes_list, build_user, repo, branch, cause):
    """
    Get or create models.Recipe records based on the input recipes.
    Input:
      recipes: list of recipe dicts as created by RecipeReader
      builduser: models.GitUser whos build key is attached to the recipe.
      owner: models.GitUser of the branch owner
      repo: models.Repository of the branch
      branch: models.Branch where this recipe will act against
      cause: models.Recipe.CAUSE* to determine what kind of recipe to create.
    Return:
      list of models.Recipe records corresponding to the input recipes
    """
    recipe_objs = []
    for r in recipes_list:
      recipe, created = models.Recipe.objects.get_or_create(
          filename=r["filename"],
          filename_sha=r["sha"],
          name=r["name"],
          display_name=r["display_name"],
          build_user=build_user,
          repository=repo,
          branch=branch,
          cause=cause,
          )
      if created:
        self.set_recipe(recipe, r, cause)
        print("Created new recipe %s: %s: %s: %s" % (recipe.name, recipe.filename, recipe.filename_sha, recipe.cause_str()))
      recipe_objs.append(recipe)
    dep_key_dict = {models.Recipe.CAUSE_MANUAL: "manual_dependencies", models.Recipe.CAUSE_PULL_REQUEST: "pullrequest_dependencies", models.Recipe.CAUSE_PUSH: "push_dependencies"}
    for (r, obj) in zip(recipes_list, recipe_objs):
      self.set_dependencies(obj, r, recipe_objs, dep_key_dict[cause])
    return recipe_objs

  def set_dependencies(self, recipe_obj, recipe_dict, recipe_objs, dep_key):
    """
    Set the models.RecipeDependency records for a recipe.
    Input:
      recipe_obj: models.Recipe to set the dependencies for
      recipe_dict: list of recipe dicts to get the names of the dependencies.
      recipe_objs: List of models.Recipe records that correspond to recipe_dict. We can only search this list as they are the only valid dependencies.
      dep_key: str: Key in the dict to get the dependency list
    """
    found = False
    for dep in recipe_dict[dep_key]:
      for r in recipe_objs:
        if r.filename == dep:
          models.RecipeDependency.objects.get_or_create(recipe=recipe_obj, dependency=r)
          found = True
          break
      if not found:
        raise Exception("Dependency not found!")

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

