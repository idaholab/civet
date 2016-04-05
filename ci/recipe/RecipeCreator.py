from ci import models

class RecipeCreator(object):
  """
  Takes a list of recipe dicts and creates records in the database.
  """
  def __init__(self):
    super(RecipeCreator, self).__init__()

  def pull_requests(self, recipes, builduser, repo):
    return self.create_recipes(recipes, builduser, repo, None, models.Recipe.CAUSE_PULL_REQUEST)

  def manual(self, recipes, builduser, owner, repo, branch):
    return self.create_recipes(recipes, owner, repo, branch, models.Recipe.CAUSE_MANUAL)

  def push(self, recipes, user, repo, branch):
    return self.create_recipes(recipes, user, repo, branch, models.Recipe.CAUSE_PUSH)

  def create_recipes(self, recipes_list, build_user, repo, branch, cause):
    recipe_objs = []
    for r in recipes_list:
      recipe, created = models.Recipe.objects.get_or_create(
          filename=r["filename"],
          filename_sha=r["filename_sha"],
          name=r["name"],
          display_name=r["display_name"],
          build_user=build_user,
          repository=repo,
          branch=branch,
          cause=cause,
          )
      if created:
        self.set_recipe(recipe, r, cause)
        print("Created new recipe %s: %s: %s" % (recipe.name, recipe.filename, recipe.filename_sha))
      recipe_objs.append(recipe)
    for (r, obj) in zip(recipes_list, recipe_objs):
      self.set_dependencies(obj, r, recipe_objs)
    return recipe_objs

  def set_dependencies(recipe_obj, recipe_dict, recipe_objs):
    for dep in recipe_dict["dependecies"]:
      for r in recipe_objs:
        if r.name == dep:
          recipe_obj.dependencies.add(r)
          break

  def set_recipe(recipe, recipe_dict, cause):
    recipe.name = recipe_dict["name"]
    recipe.display_name = recipe_dict["display_name"]
    recipe.filename = recipe_dict["filename"]
    recipe.filename_sha = recipe_dict["filename_sha"]
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
    recipe.automatic = autos[recipe["automatic"]]

    for config in recipe_dict["build_configs"]:
      bc = models.BuildConfig(name=config)
      recipe.build_configs.add(bc)

