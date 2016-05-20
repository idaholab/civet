from django.test import TestCase
from ci.tests import utils as test_utils
import shutil, os, sys
from django.conf import settings
from ci.recipe import RecipeCreator
from ci import models

class RecipeTestCase(TestCase):
  fixtures = ['base']

  def setUp(self):
    # for the RecipeRepoReader
    sys.path.insert(1, os.path.join(settings.RECIPE_BASE_DIR, "pyrecipe"))
    self.repo_dir, self.git_repo = test_utils.create_recipe_dir()
    self.recipes_dir = os.path.join(self.repo_dir, "recipes")
    os.mkdir(self.recipes_dir)
    self.orig_recipe_base_dir = settings.RECIPE_BASE_DIR
    settings.RECIPE_BASE_DIR = self.repo_dir
    self.creator = RecipeCreator.RecipeCreator(self.repo_dir)
    self.orig_timeout = settings.COLLABORATOR_CACHE_TIMEOUT
    settings.COLLABORATOR_CACHE_TIMEOUT = 0

  def tearDown(self):
    shutil.rmtree(self.repo_dir)
    settings.RECIPE_BASE_DIR = self.orig_recipe_base_dir
    settings.COLLABORATOR_CACHE_TIMEOUT = self.orig_timeout

  def create_recipe_in_repo(self, test_recipe, repo_recipe, hostname=None):
    recipe_file = self.get_recipe(test_recipe)
    if hostname:
      recipe_file = recipe_file.replace("github.com", hostname)
    return self.write_to_repo(recipe_file, repo_recipe)

  def write_script_to_repo(self, file_data, script_name):
    fname = os.path.join("scripts", script_name)
    full_fname = os.path.join(self.repo_dir, fname)
    with open(full_fname, "w") as f:
      f.write(file_data)
    self.git_repo.index.add([full_fname])
    self.git_repo.index.commit('Added script')
    return fname

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

  def load_recipes(self):
    self.creator.load_recipes()

  def create_records(self, recipe, branch):
    info = {}
    info["owner"] = test_utils.create_user(name=recipe["repository_owner"])
    info["build_user"] = test_utils.create_user_with_token(name=recipe["build_user"])
    info["repository"] = test_utils.create_repo(user=info["owner"], name=recipe["repository_name"])
    info["branch"] = test_utils.create_branch(repo=info["repository"], name=branch)
    return info

  def create_default_recipes(self, server_type=settings.GITSERVER_GITHUB):
    hostname = "github.com"
    if server_type == settings.GITSERVER_GITLAB:
      hostname = "gitlab.com"

    self.recipe_file = self.create_recipe_in_repo("recipe_all.cfg", "recipe.cfg", hostname=hostname)
    self.recipe_pr_file = self.create_recipe_in_repo("recipe_pr.cfg", "dep1.cfg", hostname=hostname)
    self.recipe_push_file = self.create_recipe_in_repo("recipe_push.cfg", "dep2.cfg", hostname=hostname)
    self.server = test_utils.create_git_server(host_type=server_type)
    self.build_user = test_utils.create_user_with_token(name="moosebuild", server=self.server)
    self.owner = test_utils.create_user(name="idaholab", server=self.server)
    self.repo = test_utils.create_repo(name="civet", user=self.owner)
    self.branch = test_utils.create_branch(name="devel", repo=self.repo)
    self.creator.load_recipes()

  def set_counts(self):
    self.num_jobs = models.Job.objects.count()
    self.num_jobs_ready = models.Job.objects.filter(ready=True).count()
    self.num_jobs_active = models.Job.objects.filter(active=True).count()
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
    self.num_push_recipes = models.Recipe.objects.filter(cause=models.Recipe.CAUSE_PUSH).count()
    self.num_pr_recipes = models.Recipe.objects.filter(cause=models.Recipe.CAUSE_PULL_REQUEST).count()
    self.num_manual_recipes = models.Recipe.objects.filter(cause=models.Recipe.CAUSE_MANUAL).count()
    self.num_pr_alt_recipes = models.Recipe.objects.filter(cause=models.Recipe.CAUSE_PULL_REQUEST_ALT).count()
    self.num_canceled = models.Job.objects.filter(status=models.JobStatus.CANCELED).count()
    self.num_invalidated = models.Job.objects.filter(invalidated=True).count()

  def compare_counts(self, jobs=0, ready=0, events=0, recipes=0, deps=0, pr_closed=False,
      current=0, sha_changed=False, users=0, repos=0, branches=0, commits=0,
      prs=0, num_push_recipes=0, num_pr_recipes=0, num_manual_recipes=0,
      num_pr_alt_recipes=0, canceled=0, invalidated=0, active=0):
    self.assertEqual(self.num_jobs + jobs, models.Job.objects.count())
    self.assertEqual(self.num_jobs_ready + ready, models.Job.objects.filter(ready=True).count())
    self.assertEqual(self.num_jobs_active + active, models.Job.objects.filter(active=True).count())
    self.assertEqual(self.num_events + events, models.Event.objects.count())
    self.assertEqual(self.num_recipes + recipes, models.Recipe.objects.count())
    self.assertEqual(self.num_recipe_deps + deps, models.RecipeDependency.objects.count())
    self.assertEqual(self.num_current + current, models.Recipe.objects.filter(current=True).count())
    self.assertEqual(self.num_users + users, models.GitUser.objects.count())
    self.assertEqual(self.num_repos + repos, models.Repository.objects.count())
    self.assertEqual(self.num_branches + branches, models.Branch.objects.count())
    self.assertEqual(self.num_commits + commits, models.Commit.objects.count())
    self.assertEqual(self.num_prs + prs, models.PullRequest.objects.count())
    self.assertEqual(self.num_push_recipes + num_push_recipes, models.Recipe.objects.filter(cause=models.Recipe.CAUSE_PUSH).count())
    self.assertEqual(self.num_pr_recipes + num_pr_recipes, models.Recipe.objects.filter(cause=models.Recipe.CAUSE_PULL_REQUEST).count())
    self.assertEqual(self.num_manual_recipes + num_manual_recipes, models.Recipe.objects.filter(cause=models.Recipe.CAUSE_MANUAL).count())
    self.assertEqual(self.num_pr_alt_recipes + num_pr_alt_recipes,  models.Recipe.objects.filter(cause=models.Recipe.CAUSE_PULL_REQUEST_ALT).count())
    self.assertEqual(self.num_canceled + canceled, models.Job.objects.filter(status=models.JobStatus.CANCELED).count())
    self.assertEqual(self.num_invalidated + invalidated, models.Job.objects.filter(invalidated=True).count())
    if sha_changed:
      self.assertNotEqual(self.repo_sha, models.RecipeRepository.load().sha)
    else:
      self.assertEqual(self.repo_sha, models.RecipeRepository.load().sha)

    if models.Event.objects.exists():
      ev = models.Event.objects.latest()
      if ev.pull_request:
        self.assertEqual(ev.pull_request.closed, pr_closed)
