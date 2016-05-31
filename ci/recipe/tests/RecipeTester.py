from ci.tests import utils as test_utils
from ci.tests import DBTester
import shutil, os, sys
from django.conf import settings
from ci.recipe import RecipeCreator
sys.path.insert(1, os.path.join(settings.RECIPE_BASE_DIR, "pyrecipe"))
import RecipeRepoReader, RecipeWriter

class RecipeTester(DBTester.DBTester):
  def setUp(self):
    super(RecipeTester, self).setUp()
    # for the RecipeRepoReader
    self.repo_dir, self.git_repo = test_utils.create_recipe_dir()
    self.recipes_dir = os.path.join(self.repo_dir, "recipes")
    os.mkdir(self.recipes_dir)
    self.orig_recipe_base_dir = settings.RECIPE_BASE_DIR
    settings.RECIPE_BASE_DIR = self.repo_dir
    self.creator = RecipeCreator.RecipeCreator(self.repo_dir)

  def tearDown(self):
    shutil.rmtree(self.repo_dir)
    settings.RECIPE_BASE_DIR = self.orig_recipe_base_dir

  def write_recipe_to_repo(self, recipe_dict, recipe_filename):
    new_recipe = RecipeWriter.write_recipe_to_string(recipe_dict)
    self.write_to_repo(new_recipe, recipe_filename)

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
    self.recipe_pr_file = self.create_recipe_in_repo("pr_dep.cfg", "pr_dep.cfg", hostname=hostname)
    self.recipe_push_file = self.create_recipe_in_repo("push_dep.cfg", "push_dep.cfg", hostname=hostname)
    self.server = test_utils.create_git_server(host_type=server_type)
    self.build_user = test_utils.create_user_with_token(name="moosebuild", server=self.server)
    self.owner = test_utils.create_user(name="idaholab", server=self.server)
    self.repo = test_utils.create_repo(name="civet", user=self.owner)
    self.branch = test_utils.create_branch(name="devel", repo=self.repo)
    self.creator.load_recipes()

  def find_recipe_dict(self, filename):
    for r in self.get_recipe_dicts():
      if r["filename"] == filename:
        return r

  def get_recipe_dicts(self):
    reader = RecipeRepoReader.RecipeRepoReader(settings.RECIPE_BASE_DIR)
    return reader.recipes
