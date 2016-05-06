from ci.recipe import RecipeCreator, RecipeFilter
import utils
from ci import models

class RecipeCreatorTests(utils.RecipeTestCase):
  def test_filter(self):
    filt = RecipeFilter.RecipeFilter(self.repo_dir)
    creator = RecipeCreator.RecipeCreator()

    self.assertEqual(len(filt.recipes), 0)

    self.create_recipe_in_repo("recipe_push.cfg", "dep2.cfg")

    filt = RecipeFilter.RecipeFilter(self.repo_dir)
    self.assertEqual(len(filt.recipes), 1)

    objs = self.create_records(filt.recipes[0], "devel")

    push = filt.find_push_recipes(objs["build_user"], objs["branch"])
    self.assertEqual(len(push), 1)
    push_objs = creator.push(push, objs["build_user"], objs["branch"])
    self.assertEqual(len(push_objs), 1)
    self.assertEqual(push_objs[0].name, push[0]["name"])
    self.assertEqual(push_objs[0].cause, models.Recipe.CAUSE_PUSH)
    self.assertEqual(push_objs[0].dependencies.count(), 0)
    self.assertEqual(models.Recipe.objects.count(), 1)

    self.create_recipe_in_repo("recipe_pr.cfg", "dep1.cfg")
    filt = RecipeFilter.RecipeFilter(self.repo_dir)
    self.assertEqual(len(filt.recipes), 2)

    pr = filt.find_pr_recipes(objs["build_user"], objs["repository"])
    self.assertEqual(len(pr), 1)
    pr_objs = creator.pull_requests(pr, objs["build_user"], objs["repository"])
    self.assertEqual(len(pr_objs), 1)
    self.assertEqual(pr_objs[0].name, pr[0]["name"])
    self.assertEqual(pr_objs[0].cause, models.Recipe.CAUSE_PULL_REQUEST)
    self.assertEqual(push_objs[0].dependencies.count(), 0)
    self.assertEqual(models.Recipe.objects.count(), 2)

    self.create_recipe_in_repo("recipe_all.cfg", "recipe.cfg")
    filt = RecipeFilter.RecipeFilter(self.repo_dir)
    self.assertEqual(len(filt.recipes), 3)

    pr = filt.find_pr_recipes(objs["build_user"], objs["repository"])
    self.assertEqual(len(pr), 2)
    pr_objs = creator.pull_requests(pr, objs["build_user"], objs["repository"])
    self.assertEqual(len(pr_objs), 2)
    self.assertEqual(pr_objs[0].name, pr[0]["name"])
    self.assertEqual(pr_objs[0].cause, models.Recipe.CAUSE_PULL_REQUEST)
    self.assertEqual(pr_objs[1].name, pr[1]["name"])
    self.assertEqual(pr_objs[1].cause, models.Recipe.CAUSE_PULL_REQUEST)
    self.assertEqual(pr_objs[0].dependencies.count(), 0)
    self.assertEqual(pr_objs[1].dependencies.count(), 1)
    self.assertEqual(pr_objs[1].dependencies.first(), pr_objs[0])
    self.assertEqual(models.Recipe.objects.count(), 3)

    push = filt.find_push_recipes(objs["build_user"], objs["branch"])
    push_objs = creator.push(push, objs["build_user"], objs["branch"])
    self.assertEqual(len(push_objs), 2)
    self.assertEqual(push_objs[0].name, push[0]["name"])
    self.assertEqual(push_objs[0].cause, models.Recipe.CAUSE_PUSH)
    self.assertEqual(push_objs[1].name, push[1]["name"])
    self.assertEqual(push_objs[1].cause, models.Recipe.CAUSE_PUSH)
    self.assertEqual(push_objs[0].dependencies.count(), 0)
    self.assertEqual(push_objs[1].dependencies.count(), 1)
    self.assertEqual(push_objs[1].dependencies.first(), push_objs[0])
    self.assertEqual(models.Recipe.objects.count(), 4)

    manual = filt.find_manual_recipes(objs["build_user"], objs["branch"])
    self.assertEqual(len(manual), 1)
    manual_objs = creator.manual(manual, objs["build_user"], objs["branch"])
    self.assertEqual(len(manual_objs), 1)
    self.assertEqual(manual_objs[0].name, manual[0]["name"])
    self.assertEqual(manual_objs[0].cause, models.Recipe.CAUSE_MANUAL)
    self.assertEqual(manual_objs[0].dependencies.count(), 0)
    self.assertEqual(models.Recipe.objects.count(), 5)

    alt_pr = filt.find_alt_pr_recipes(objs["build_user"], objs["repository"])
    self.assertEqual(len(alt_pr), 1)
    alt_pr_objs = creator.pull_requests(alt_pr, objs["build_user"], objs["repository"])
    self.assertEqual(len(alt_pr_objs), 1)
    self.assertEqual(alt_pr_objs[0].name, alt_pr[0]["name"])
    self.assertEqual(alt_pr_objs[0].cause, models.Recipe.CAUSE_PULL_REQUEST)
    self.assertEqual(alt_pr_objs[0].dependencies.count(), 0)
    self.assertEqual(models.Recipe.objects.count(), 6)

    self.assertEqual(alt_pr_objs[0].filename_sha, push_objs[0].filename_sha)
    self.assertNotEqual(alt_pr_objs[0].filename_sha, manual_objs[0].filename_sha)
    self.assertNotEqual(alt_pr_objs[0].filename_sha, pr_objs[0].filename_sha)
