from ci.recipe import RecipeCreator, RecipeRepoReader, RecipeWriter
import utils
from ci.tests import utils as test_utils
from ci import models
from django.conf import settings

class RecipeCreatorTests(utils.RecipeTestCase):
  def test_load_recipes(self):
    # no recipes, nothing to do
    creator = RecipeCreator.RecipeCreator(self.repo_dir)
    self.set_counts()
    creator.load_recipes()
    self.compare_counts(sha_changed=True)

    # moosebuild user doesn't exist
    self.set_counts()
    self.create_recipe_in_repo("recipe_push.cfg", "dep2.cfg")
    with self.assertRaises(RecipeRepoReader.InvalidRecipe):
      creator.load_recipes()
    self.compare_counts()

    # OK
    server = test_utils.create_git_server(name="github.com")
    moosebuild = test_utils.create_user(name="moosebuild", server=server)
    self.set_counts()
    creator.load_recipes()
    self.compare_counts(recipes=2, current=2, sha_changed=True, users=1, repos=1, branches=1, num_push_recipes=1, num_pr_alt_recipes=1)

    # dependency file doesn't exist
    self.set_counts()
    self.create_recipe_in_repo("recipe_all.cfg", "all.cfg")
    with self.assertRaises(RecipeRepoReader.InvalidRecipe):
      creator.load_recipes()
    self.compare_counts()

    # dependency file isn't valid
    self.set_counts()
    self.create_recipe_in_repo("recipe_push.cfg", "dep1.cfg")
    with self.assertRaises(RecipeRepoReader.InvalidDependency):
      creator.load_recipes()
    self.compare_counts()

    # OK
    self.set_counts()
    self.create_recipe_in_repo("recipe_pr.cfg", "dep1.cfg")
    creator.load_recipes()
    self.compare_counts(recipes=4, sha_changed=True, current=4, deps=2, num_push_recipes=1, num_manual_recipes=1, num_pr_recipes=2)

    # OK, repo sha hasn't changed so no changes.
    self.set_counts()
    creator.load_recipes()
    self.compare_counts()

    # a recipe changed, should have a new recipe but since
    # none of the recipes have jobs attached, the old ones
    # will get deleted and get recreated.
    reader = RecipeRepoReader.RecipeRepoReader(settings.RECIPE_BASE_DIR)
    self.assertEqual(len(reader.recipes), 3)
    pr_recipe = None
    for r in reader.recipes:
      if r["filename"] == "recipes/dep1.cfg":
        pr_recipe = r
    pr_recipe["priority_pull_request"] = 100
    new_recipe = RecipeWriter.write_recipe_to_string(pr_recipe)
    self.write_to_repo(new_recipe, "dep1.cfg")
    self.set_counts()
    creator.load_recipes()
    self.compare_counts(sha_changed=True)

    # change a recipe but now the old ones have jobs attached.
    # so 1 new recipe should be added
    for r in models.Recipe.objects.all():
      test_utils.create_job(recipe=r, user=moosebuild)
    pr_recipe["priority_pull_request"] = 99
    new_recipe = RecipeWriter.write_recipe_to_string(pr_recipe)
    self.write_to_repo(new_recipe, "dep1.cfg")
    self.set_counts()
    creator.load_recipes()
    self.compare_counts(sha_changed=True, recipes=1, num_pr_recipes=1)
    q = models.Recipe.objects.filter(filename=pr_recipe["filename"])
    self.assertEqual(q.count(), 2)
    q = q.filter(current=True)
    self.assertEqual(q.count(), 1)
    new_r = q.first()
    q = models.Recipe.objects.filter(filename=new_r.filename).exclude(pk=new_r.pk)
    self.assertEqual(q.count(), 1)
    old_r = q.first()
    self.assertNotEqual(old_r.filename_sha, new_r.filename_sha)
