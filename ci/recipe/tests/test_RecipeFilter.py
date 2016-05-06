from ci.recipe import RecipeFilter
import utils

class RecipeFilterTests(utils.RecipeTestCase):
  def test_filter(self):
    filt = RecipeFilter.RecipeFilter(self.repo_dir)
    self.assertEqual(len(filt.recipes), 0)

    self.create_recipe_in_repo("recipe_all.cfg", "recipe.cfg")
    self.create_recipe_in_repo("recipe_pr.cfg", "dep1.cfg")
    self.create_recipe_in_repo("recipe_push.cfg", "dep2.cfg")

    filt = RecipeFilter.RecipeFilter(self.repo_dir)
    self.assertEqual(len(filt.recipes), 3)

    objs = self.create_records(filt.recipes[0], "devel")

    push = filt.find_push_recipes(objs["build_user"], objs["branch"])
    self.assertEqual(len(push), 2)

    pr = filt.find_pr_recipes(objs["build_user"], objs["repository"])
    self.assertEqual(len(pr), 2)

    manual = filt.find_manual_recipes(objs["build_user"], objs["branch"])
    self.assertEqual(len(manual), 1)

    alt_pr = filt.find_alt_pr_recipes(objs["build_user"], objs["repository"])
    self.assertEqual(len(alt_pr), 1)
