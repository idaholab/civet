from ci.recipe import recipe
import utils
from ci import models

class RecipeTests(utils.RecipeTestCase):
  def setUp(self):
    super(RecipeTests, self).setUp()
    self.create_default_recipes()

  def set_counts(self):
    self.num_recipes = models.Recipe.objects.count()
    self.num_recipe_deps = models.RecipeDependency.objects.count()

  def compare_counts(self, recipes=0, deps=0):
    self.assertEqual(self.num_recipes + recipes, models.Recipe.objects.count())
    self.assertEqual(self.num_recipe_deps + deps, models.RecipeDependency.objects.count())

  def test_get_push_recipes(self):
    self.set_counts()
    push = recipe.get_push_recipes(self.build_user, self.branch)
    self.assertEqual(len(push), 2)
    self.compare_counts(recipes=2, deps=1)

    # recipes already exist, nothing should change
    self.set_counts()
    recipe.get_push_recipes(self.build_user, self.branch)
    self.compare_counts()

  def test_get_manual_recipes(self):
    self.set_counts()
    manual = recipe.get_manual_recipes(self.build_user, self.branch)
    self.assertEqual(len(manual), 1)
    self.compare_counts(recipes=1)

    # recipes already exist, nothing should change
    self.set_counts()
    recipe.get_manual_recipes(self.build_user, self.branch)
    self.compare_counts()

  def test_get_pr_recipes(self):
    self.set_counts()
    prs = recipe.get_pr_recipes(self.build_user, self.repo)
    self.assertEqual(len(prs), 2)
    self.compare_counts(recipes=2, deps=1)

    # recipes already exist, nothing should change
    self.set_counts()
    prs = recipe.get_pr_recipes(self.build_user, self.repo)
    self.compare_counts()
