from ci.recipe import RecipeReader
import utils

class RecipeReaderTests(utils.RecipeTestCase):
  def test_read(self):
    fname = self.create_recipe_in_repo("recipe_all.cfg", "recipe.cfg")
    self.create_recipe_in_repo("recipe_push.cfg", "dep1.cfg")
    self.create_recipe_in_repo("recipe_pr.cfg", "dep2.cfg")
    reader = RecipeReader.RecipeReader(self.repo_dir, fname)
    r = reader.read()
    self.assertEqual(r.get("name"), "Test Recipe")
    self.assertEqual(r.get("display_name"), "Display Recipe")
    self.assertEqual(len(r.get("sha")), 40)
    self.assertEqual(len(r.get("repo_sha")), 40)
    self.assertEqual(r.get("repository"), "git@github.com:idaholab/civet.git")
    self.assertEqual(r.get("private"), False)
    self.assertEqual(r.get("active"), True)
    self.assertEqual(r.get("automatic"), "authorized")
    self.assertEqual(r.get("build_user"), "moosebuild")
    self.assertEqual(r.get("build_configs"), ["linux-gnu"])
    self.assertEqual(r.get("trigger_push"), True)
    self.assertEqual(r.get("trigger_push_branch"), "devel")
    self.assertEqual(r.get("priority_push"), 1)
    self.assertEqual(r.get("trigger_pull_request"), True)
    self.assertEqual(r.get("priority_pull_request"), 2)
    self.assertEqual(r.get("trigger_manual"), True)
    self.assertEqual(r.get("trigger_manual_branch"), "devel")
    self.assertEqual(r.get("priority_manual"), 3)
    self.assertEqual(r.get("allow_on_pr"), True)

    global_env = r.get("global_env")
    self.assertEqual(len(global_env.keys()), 2)
    self.assertEqual(global_env.get("APPLICATION_NAME"), "civet")
    self.assertEqual(global_env.get("MOOSE_DIR"), "BUILD_ROOT/moose")

    global_sources = r.get("global_sources")
    self.assertEqual(len(global_sources), 2)
    self.assertEqual(global_sources, ["scripts/1.sh", "scripts/2.sh"])

    pr_deps = r.get("pullrequest_dependencies")
    self.assertEqual(len(pr_deps), 1)
    self.assertEqual(pr_deps, ["recipes/dep1.cfg"])

    push_deps = r.get("push_dependencies")
    self.assertEqual(len(push_deps), 1)
    self.assertEqual(push_deps, ["recipes/dep2.cfg"])

    manual_deps = r.get("manual_dependencies")
    self.assertEqual(len(manual_deps), 0)

    steps = r.get("steps")
    self.assertEqual(len(steps), 2)
    self.assertEqual(steps[0].get("name"), "Pre Test")
    self.assertEqual(steps[0].get("script"), "scripts/1.sh")
    self.assertEqual(steps[0].get("abort_on_failure"), True)
    self.assertEqual(steps[0].get("allowed_to_fail"), True)
    self.assertEqual(len(steps[0].get("environment").keys()), 4)
    self.assertEqual(steps[0].get("environment").get("FOO"), "bar")

    self.assertEqual(steps[1].get("name"), "Next Step")
    self.assertEqual(steps[1].get("script"), "scripts/2.sh")
    self.assertEqual(steps[1].get("abort_on_failure"), False)
    self.assertEqual(steps[1].get("allowed_to_fail"), False)
    self.assertEqual(len(steps[1].get("environment").keys()), 4)
    self.assertEqual(steps[1].get("environment").get("ENV"), "some string")

  def test_check(self):
    fname = self.create_recipe_in_repo("recipe_all.cfg", "recipe.cfg")
    self.create_recipe_in_repo("recipe_push.cfg", "dep1.cfg")
    self.create_recipe_in_repo("recipe_pr.cfg", "dep2.cfg")
    reader = RecipeReader.RecipeReader(self.repo_dir, fname)
    r = reader.read()
    self.assertEqual(reader.check(), True)
    self.assertNotEqual(r, {})

    good_recipe = reader.recipe.copy()
    reader.recipe["display_name"] = ""
    self.assertEqual(reader.check(), True)
    self.assertEqual(reader.recipe["display_name"], reader.recipe["name"])

    reader.recipe["automatic"] = "foo"
    self.assertEqual(reader.check(), False)

    reader.recipe = good_recipe.copy()
    reader.recipe["trigger_pull_request"] = False
    reader.recipe["trigger_push"] = False
    reader.recipe["trigger_manual"] = False
    reader.recipe["allow_on_pr"] = False
    self.assertEqual(reader.check(), False)

    reader.recipe = good_recipe.copy()
    reader.recipe["trigger_push"] = True
    reader.recipe["trigger_push_branch"] = ""
    self.assertEqual(reader.check(), False)

    reader.recipe = good_recipe.copy()
    reader.recipe["trigger_manual"] = True
    reader.recipe["trigger_manual_branch"] = ""
    self.assertEqual(reader.check(), False)

    reader.recipe = good_recipe.copy()
    reader.recipe["sha"] = ""
    self.assertEqual(reader.check(), False)

    reader.recipe = good_recipe.copy()
    reader.recipe["repo_sha"] = ""
    self.assertEqual(reader.check(), False)

    reader.recipe = good_recipe.copy()
    reader.recipe["build_configs"] = []
    self.assertEqual(reader.check(), False)

    reader.recipe["build_configs"] = ["foo", "bar"]
    self.assertEqual(reader.check(), False)

    reader.recipe = good_recipe.copy()
    reader.recipe["repository"] = "not an url"
    self.assertEqual(reader.check(), False)

    reader.recipe = good_recipe.copy()
    reader.recipe["global_sources"] = ["not a file"]
    self.assertEqual(reader.check(), False)

    reader.recipe = good_recipe.copy()
    reader.recipe["pullrequest_dependencies"] = ["not a file"]
    self.assertEqual(reader.check(), False)
    reader.recipe["pullrequest_dependencies"] = [fname]
    self.assertEqual(reader.check(), False)

    reader.recipe = good_recipe.copy()
    reader.recipe["push_dependencies"] = ["not a file"]
    self.assertEqual(reader.check(), False)
    reader.recipe["push_dependencies"] = [fname]
    self.assertEqual(reader.check(), False)

    reader.recipe = good_recipe.copy()
    reader.recipe["manual_dependencies"] = ["not a file"]
    self.assertEqual(reader.check(), False)
    reader.recipe["manual_dependencies"] = [fname]
    self.assertEqual(reader.check(), False)


    reader.recipe = good_recipe.copy()
    reader.recipe["steps"] = []
    self.assertEqual(reader.check(), False)

    reader.recipe = good_recipe.copy()
    reader.recipe["steps"][0]["script"] = "not a file"
    self.assertEqual(reader.check(), False)
