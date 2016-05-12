from ci.recipe import RecipeReader, RecipeWriter
import utils

class RecipeWriterTests(utils.RecipeTestCase):
  def test_write(self):
    fname = self.create_recipe_in_repo("recipe_all.cfg", "recipe.cfg")
    self.create_recipe_in_repo("recipe_push.cfg", "dep1.cfg")
    self.create_recipe_in_repo("recipe_pr.cfg", "dep2.cfg")
    reader = RecipeReader.RecipeReader(self.repo_dir, fname)
    r = reader.read()
    self.assertEqual(r.get("repository"), "git@github.com:idaholab/civet.git")
    r["repository"] = "new_repo"

    global_env = r.get("global_env")
    self.assertEqual(len(global_env.keys()), 2)
    r["global_env"]["APPLICATION_NAME"] = "new_app"

    global_sources = r.get("global_sources")
    self.assertEqual(len(global_sources), 2)
    r["global_sources"][0] = "new_source"

    deps = r.get("pullrequest_dependencies")
    self.assertEqual(len(deps), 1)
    r["pullrequest_dependencies"][0] = "new_dep"

    steps = r.get("steps")
    self.assertEqual(len(steps), 2)
    r["steps"][0]["name"] = "new_step"

    self.assertTrue(RecipeWriter.write_recipe_to_repo(self.repo_dir, r, "new_file.cfg"))
    reader = RecipeReader.RecipeReader(self.repo_dir, "new_file.cfg")
    r = reader.read()
    # we changed the source and the dep so now the recipe doesn't pass the check.
    self.assertEqual(r, {})
    r = reader.read(do_check=False)
    self.assertEqual(r["repository"], "new_repo")
    self.assertEqual(r["global_env"]["APPLICATION_NAME"], "new_app")
    self.assertEqual(r["global_sources"][0], "new_source")
    self.assertEqual(r["pullrequest_dependencies"][0], "new_dep")
    self.assertEqual(r["steps"][0]["name"], "new_step")
