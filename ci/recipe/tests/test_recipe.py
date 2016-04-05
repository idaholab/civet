from django.test import TestCase
from ci.recipe import recipe
from ci.tests import utils
import shutil, os

class RecipeTestCase(TestCase):
  fixtures = ['base']

  def setUp(self):
    self.recipe_dir, self.repo = utils.create_recipe_dir()
    recipes = os.path.join(self.recipe_dir, "recipes")
    os.mkdir(recipes)
    recipe_file = self.get_recipe("recipe.cfg")
    self.test_recipe_file = os.path.join(recipes, "recipe.cfg")
    with open(self.test_recipe_file, "w") as f:
      f.write(recipe_file)
    self.repo.index.add([self.test_recipe_file])
    self.repo.index.commit('Added recipe')

  def get_recipe(self, fname):
    p = '{}/{}'.format(os.path.dirname(__file__), fname)
    with open(p, 'r') as f:
      contents = f.read()
      return contents

  def tearDown(self):
    shutil.rmtree(self.recipe_dir)

  def test_recipe_list(self):
    recipes = recipe.recipe_list(self.recipe_dir)
    self.assertEqual(len(recipes), 1)
    r = recipes[0]
    self.assertEqual(r.get("name"), "Test Recipe")
    self.assertEqual(r.get("display_name"), "Display Recipe")
    self.assertEqual(len(r.get("sha")), 40)
    self.assertEqual(len(r.get("repo_sha")), 40)
    self.assertEqual(r.get("private"), False)
    self.assertEqual(r.get("active"), True)
    self.assertEqual(r.get("automatic"), "authorized")
    self.assertEqual(r.get("build_user"), "moosebuild")
    self.assertEqual(r.get("build_configs"), ["linux-gnu"])
    self.assertEqual(r.get("trigger_push"), True)
    self.assertEqual(r.get("trigger_push_branch"), "devel")
    global_env = r.get("global_env")
    self.assertEqual(len(global_env.keys()), 2)
    self.assertEqual(global_env.get("APPLICATION_NAME"), "moose")
    self.assertEqual(global_env.get("MOOSE_DIR"), "BUILD_ROOT/moose")
    global_sources = r.get("global_sources")
    self.assertEqual(len(global_sources), 2)
    self.assertEqual(global_sources, ["common/env.sh", "common/env_pre_check.sh"])
    steps = r.get("steps")
    self.assertEqual(len(steps), 2)
    self.assertEqual(steps[0].get("name"), "Pre Test")
    self.assertEqual(steps[0].get("script"), "common/pre_check.sh")
    self.assertEqual(steps[0].get("abort_on_failure"), True)
    self.assertEqual(steps[0].get("allowed_to_fail"), True)
    self.assertEqual(len(steps[0].get("environment").keys()), 4)
    self.assertEqual(steps[0].get("environment").get("FOO"), "bar")

    self.assertEqual(steps[1].get("name"), "Next Step")
    self.assertEqual(steps[1].get("script"), "common/pre_check.sh")
    self.assertEqual(steps[1].get("abort_on_failure"), False)
    self.assertEqual(steps[1].get("allowed_to_fail"), False)
    self.assertEqual(len(steps[1].get("environment").keys()), 4)
    self.assertEqual(steps[1].get("environment").get("ENV"), "some string")
