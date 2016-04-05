import settings
import RecipeFilter, RecipeCreator

def get_pr_recipes(builduser, repo):
  rfilter = RecipeFilter(settings.RECIPE_BASE_DIR)
  rcreator = RecipeCreator()
  return rcreator.pull_requests(rfilter.find_pr_recipes(builduser, repo))

def get_manual_recipes(builduser, branch):
  rfilter = RecipeFilter(settings.RECIPE_BASE_DIR)
  rcreator = RecipeCreator()
  return rcreator.manual(rfilter.find_manual_recipes(builduser, branch.repository.user, branch.repository, branch))

def get_push_recipes(user, repo, branch):
  rfilter = RecipeFilter(settings.RECIPE_BASE_DIR)
  rcreator = RecipeCreator()
  return rcreator.push(rfilter.find_push_recipes(user, repo, branch))
