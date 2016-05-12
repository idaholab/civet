from django.test import TestCase
from ci.tests import utils as test_utils
import shutil, os
from ci.recipe import utils as recipe_utils
from django.conf import settings
from ci import models

class RecipeTestCase(TestCase):
  fixtures = ['base']

  def setUp(self):
    self.repo_dir, self.git_repo = test_utils.create_recipe_dir()
    self.recipes_dir = os.path.join(self.repo_dir, "recipes")
    os.mkdir(self.recipes_dir)
    self.orig_recipe_base_dir = settings.RECIPE_BASE_DIR
    settings.RECIPE_BASE_DIR = self.repo_dir

  def tearDown(self):
    shutil.rmtree(self.repo_dir)
    settings.RECIPE_BASE_DIR = self.orig_recipe_base_dir

  def create_recipe_in_repo(self, test_recipe, repo_recipe, hostname=None):
    recipe_file = self.get_recipe(test_recipe)
    if hostname:
      recipe_file = recipe_file.replace("github.com", hostname)
    return self.write_to_repo(recipe_file, repo_recipe)

  def write_to_repo(self, file_data, repo_recipe):
    fname = os.path.join("recipes", repo_recipe)
    full_fname = os.path.join(self.recipes_dir, repo_recipe)
    with open(full_fname, "w") as f:
      f.write(file_data)
    self.git_repo.index.add([full_fname])
    self.git_repo.index.commit('Added recipe')
    return fname

  def get_recipe(self, fname):
    p = '{}/{}'.format(os.path.dirname(__file__), fname)
    with open(p, 'r') as f:
      contents = f.read()
      return contents

  def create_records(self, recipe, branch):
    info = {}
    server_name, owner_name, repo_name = recipe_utils.parse_repo(recipe["repository"])
    info["owner"] = test_utils.create_user(name=owner_name)
    info["build_user"] = test_utils.create_user(name=recipe["build_user"])
    info["repository"] = test_utils.create_repo(user=info["owner"], name=repo_name)
    info["branch"] = test_utils.create_branch(repo=info["repository"], name=branch)
    return info

  def create_default_recipes(self, server_type=settings.GITSERVER_GITHUB):
    hostname = "github.com"
    if server_type == settings.GITSERVER_GITLAB:
      hostname = "gitlab.com"

    self.create_recipe_in_repo("recipe_all.cfg", "recipe.cfg", hostname=hostname)
    self.create_recipe_in_repo("recipe_pr.cfg", "dep1.cfg", hostname=hostname)
    self.create_recipe_in_repo("recipe_push.cfg", "dep2.cfg", hostname=hostname)
    self.server = test_utils.create_git_server(host_type=server_type)
    self.build_user = test_utils.create_user_with_token(name="moosebuild", server=self.server)
    self.owner = test_utils.create_user(name="idaholab", server=self.server)
    self.repo = test_utils.create_repo(name="civet", user=self.owner)
    self.branch = test_utils.create_branch(name="devel", repo=self.repo)

  def set_counts(self):
    self.num_jobs = models.Job.objects.count()
    self.num_jobs_ready = models.Job.objects.filter(ready=True).count()
    self.num_events = models.Event.objects.count()
    self.num_recipes = models.Recipe.objects.count()
    self.num_recipe_deps = models.RecipeDependency.objects.count()
    self.num_current = models.Recipe.objects.filter(current=True).count()
    self.repo_sha = models.RecipeRepository.load().sha
    self.num_users = models.GitUser.objects.count()
    self.num_repos = models.Repository.objects.count()
    self.num_branches = models.Branch.objects.count()
    self.num_commits = models.Commit.objects.count()
    self.num_prs = models.PullRequest.objects.count()

  def compare_counts(self, jobs=0, ready=0, events=0, recipes=0, deps=0, pr_closed=False, current=0, sha_changed=False, users=0, repos=0, branches=0, commits=0, prs=0):
    self.assertEqual(self.num_jobs + jobs, models.Job.objects.count())
    self.assertEqual(self.num_jobs_ready + ready, models.Job.objects.filter(ready=True).count())
    self.assertEqual(self.num_events + events, models.Event.objects.count())
    self.assertEqual(self.num_recipes + recipes, models.Recipe.objects.count())
    self.assertEqual(self.num_recipe_deps + deps, models.RecipeDependency.objects.count())
    self.assertEqual(self.num_current + current, models.Recipe.objects.filter(current=True).count())
    self.assertEqual(self.num_users + users, models.GitUser.objects.count())
    self.assertEqual(self.num_repos + repos, models.Repository.objects.count())
    self.assertEqual(self.num_branches + branches, models.Branch.objects.count())
    self.assertEqual(self.num_commits + commits, models.Commit.objects.count())
    self.assertEqual(self.num_prs + prs, models.PullRequest.objects.count())
    if sha_changed:
      self.assertNotEqual(self.repo_sha, models.RecipeRepository.load().sha)
    else:
      self.assertEqual(self.repo_sha, models.RecipeRepository.load().sha)

    if models.Event.objects.exists():
      ev = models.Event.objects.latest()
      if ev.pull_request:
        self.assertEqual(ev.pull_request.closed, pr_closed)
