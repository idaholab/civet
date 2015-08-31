from django.test import TestCase
from django.conf import settings
from ci import models
from . import utils

class ModelTestCase(TestCase):
#  fixtures = ['base', 'dummy']

  def test_git_server(self):
    server = utils.create_git_server(host_type=settings.GITSERVER_GITHUB)
    self.assertTrue(isinstance(server, models.GitServer))
    self.assertEqual(server.__unicode__(), server.name)
    self.assertNotEqual(server.api(), None)
    self.assertNotEqual(server.auth(), None)
    server = utils.create_git_server(host_type=settings.GITSERVER_GITLAB)
    self.assertNotEqual(server.api(), None)
    self.assertNotEqual(server.auth(), None)
    server = utils.create_git_server(host_type=settings.GITSERVER_BITBUCKET)
    self.assertEqual(server.api(), None)
    self.assertEqual(server.auth(), None)

  def test_git_user(self):
    user = utils.create_user()
    self.assertTrue(isinstance(user, models.GitUser))
    self.assertEqual(user.__unicode__(), user.name)
    session = user.start_session()
    self.assertNotEqual(session, None)

  def test_repository(self):
    repo = utils.create_repo()
    self.assertTrue(isinstance(repo, models.Repository))
    self.assertIn(repo.name, repo.__unicode__())
    self.assertIn(repo.user.name, repo.__unicode__())
    url = repo.url()
    self.assertIn(repo.user.name, url)
    self.assertIn(repo.name, url)

  def test_branch(self):
    branch = utils.create_branch()
    self.assertTrue(isinstance(branch, models.Branch))
    self.assertIn(branch.repository.name, branch.__unicode__())
    self.assertIn(branch.repository.user.name, branch.__unicode__())
    self.assertIn(branch.name, branch.__unicode__())
    server = branch.server()
    self.assertEqual(server, branch.repository.user.server)
    user = branch.user()
    self.assertEqual(user, branch.repository.user)

  def test_commit(self):
    commit = utils.create_commit()
    self.assertTrue(isinstance(commit, models.Commit))
    self.assertIn(commit.branch.name, commit.__unicode__())
    self.assertIn(commit.sha, commit.__unicode__())

  def test_event(self):
    event = utils.create_event()
    self.assertTrue(isinstance(event, models.Event))
    self.assertIn('Pull', event.__unicode__())
    self.assertIn('Pull', event.cause_str())
    with self.assertRaises(Exception):
      utils.create_event(commit1="3456", host_type=10)
    user = event.user()
    self.assertEqual(event.head.user(), user)

  def test_pullrequest(self):
    pr = utils.create_pr()
    self.assertTrue(isinstance(pr, models.PullRequest))
    self.assertIn(pr.title, pr.__unicode__())

  def test_buildconfig(self):
    bc = utils.create_build_config()
    self.assertTrue(isinstance(bc, models.BuildConfig))
    self.assertIn(bc.name, bc.__unicode__())

  def test_recipe(self):
    rc = utils.create_recipe()
    self.assertTrue(isinstance(rc, models.Recipe))
    self.assertIn(rc.name, rc.__unicode__())
    with self.assertRaises(Exception):
      utils.create_recipe(name='testRecipe2', host_type=10)

    self.assertEqual(rc.auto_str(), models.Recipe.AUTO_CHOICES[rc.automatic][1])
    self.assertEqual(rc.cause_str(), models.Recipe.CAUSE_CHOICES[rc.cause][1])
    self.assertTrue(isinstance(rc.configs_str(), basestring))

  def test_recipeenv(self):
    renv = utils.create_recipe_environment()
    self.assertTrue(isinstance(renv, models.RecipeEnvironment))
    self.assertIn(renv.name, renv.__unicode__())
    self.assertIn(renv.value, renv.__unicode__())

  def test_recipedepend(self):
    rd = utils.create_recipe_dependency()
    self.assertTrue(isinstance(rd, models.RecipeDependency))
    self.assertIn('recipe1', rd.__unicode__())
    self.assertIn('recipe2', rd.__unicode__())

  def test_prestepsource(self):
    s = utils.create_prestepsource()
    self.assertTrue(isinstance(s, models.PreStepSource))
    self.assertIn(s.filename, s.__unicode__())

  def test_step(self):
    s = utils.create_step()
    self.assertTrue(isinstance(s, models.Step))
    self.assertIn(s.name, s.__unicode__())

  def test_stepenvironment(self):
    se = utils.create_step_environment()
    self.assertTrue(isinstance(se, models.StepEnvironment))
    self.assertIn(se.name, se.__unicode__())
    self.assertIn(se.value, se.__unicode__())

  def test_client(self):
    c = utils.create_client()
    self.assertTrue(isinstance(c, models.Client))
    self.assertIn(c.name, c.__unicode__())

  def test_job(self):
    j = utils.create_job()
    self.assertTrue(isinstance(j, models.Job))
    self.assertIn(j.recipe.name, j.__unicode__())

  def test_stepresult(self):
    sr = utils.create_step_result()
    self.assertTrue(isinstance(sr, models.StepResult))
    self.assertIn(sr.step.name, sr.__unicode__())
    self.assertEqual(models.JobStatus.to_slug(sr.status), sr.status_slug())

  def test_token(self):
    user = utils.create_user_with_token()
    self.assertTrue(isinstance(user.token, models.OAuthToken))
    self.assertIn(user.token.token, user.token.__unicode__())

  def test_generate_build_key(self):
    build_key = models.generate_build_key()
    self.assertNotEqual('', build_key)

  def test_jobstatus(self):
    for i in models.JobStatus.STATUS_CHOICES:
        self.assertEqual(models.JobStatus.to_str(i[0]), i[1])
    for i in models.JobStatus.SHORT_CHOICES:
        self.assertEqual(models.JobStatus.to_slug(i[0]), i[1])
