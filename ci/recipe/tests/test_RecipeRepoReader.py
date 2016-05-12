from ci.recipe import RecipeRepoReader
from ci.recipe import RecipeWriter
import utils

class RecipeRepoReaderTests(utils.RecipeTestCase):
  def test_reader(self):
    reader = RecipeRepoReader.RecipeRepoReader(self.repo_dir)
    self.assertEqual(len(reader.recipes), 0)

    self.create_recipe_in_repo("recipe_all.cfg", "recipe.cfg")
    with self.assertRaises(RecipeRepoReader.InvalidRecipe):
      reader = RecipeRepoReader.RecipeRepoReader(self.repo_dir)

    self.create_recipe_in_repo("recipe_pr.cfg", "dep1.cfg")
    with self.assertRaises(RecipeRepoReader.InvalidRecipe):
      reader = RecipeRepoReader.RecipeRepoReader(self.repo_dir)

    self.create_recipe_in_repo("recipe_push.cfg", "dep2.cfg")
    reader = RecipeRepoReader.RecipeRepoReader(self.repo_dir)
    self.assertEqual(len(reader.recipes), 3)

    recipe = reader.recipes[2]
    recipe["build_user"] = "no_exist"
    RecipeWriter.write_recipe_to_repo(self.repo_dir, recipe, recipe["filename"])
    with self.assertRaises(RecipeRepoReader.InvalidDependency):
      reader = RecipeRepoReader.RecipeRepoReader(self.repo_dir)
