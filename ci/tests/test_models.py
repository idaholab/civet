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
    self.assertNotEqual(server.api(), None)
    self.assertNotEqual(server.auth(), None)

  def test_git_user(self):
    user = utils.create_user()
    self.assertTrue(isinstance(user, models.GitUser))
    self.assertEqual(user.__unicode__(), user.name)
    session = user.start_session()
    self.assertNotEqual(session, None)
    self.assertNotEqual(user.api(), None)
    self.assertEqual(user.token, '')

  def test_repository(self):
    repo = utils.create_repo()
    self.assertTrue(isinstance(repo, models.Repository))
    self.assertIn(repo.name, repo.__unicode__())
    self.assertIn(repo.user.name, repo.__unicode__())
    url = repo.url()
    self.assertIn(repo.user.name, url)
    self.assertIn(repo.name, url)
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
    self.assertNotEqual(branch.status_slug(), None)

  def test_commit(self):
    commit = utils.create_commit()
    self.assertTrue(isinstance(commit, models.Commit))
    self.assertIn(commit.branch.name, commit.__unicode__())
    self.assertIn(commit.sha, commit.__unicode__())
    self.assertEqual(commit.server(), commit.branch.repository.user.server)
    self.assertEqual(commit.repo(), commit.branch.repository)
    self.assertNotEqual(commit.url(), None)

  def test_event(self):
    event = utils.create_event()
    self.assertTrue(isinstance(event, models.Event))
    self.assertIn('Pull', event.__unicode__())
    self.assertIn('Pull', event.cause_str())
    event.cause = models.Event.PUSH
    event.save()
    self.assertIn('Push', event.cause_str())
    # duplicate commits
    with self.assertRaises(Exception):
      utils.create_event()
    user = event.user()
    self.assertEqual(event.head.user(), user)
    self.assertNotEqual(event.status_slug(), None)

    r0 = utils.create_recipe(name='r0')
    r1 = utils.create_recipe(name='r1')
    r2 = utils.create_recipe(name='r2')
    r3 = utils.create_recipe(name='r3')
    r4 = utils.create_recipe(name='r4')
    utils.create_recipe_dependency(recipe=r1 , depends_on=r0)
    utils.create_recipe_dependency(recipe=r3, depends_on=r0)
    utils.create_recipe_dependency(recipe=r4, depends_on=r0)
    utils.create_recipe_dependency(recipe=r2, depends_on=r1)
    utils.create_recipe_dependency(recipe=r2, depends_on=r3)
    utils.create_recipe_dependency(recipe=r2, depends_on=r4)
    utils.create_job(recipe=r0, event=event)
    utils.create_job(recipe=r1, event=event)
    utils.create_job(recipe=r2, event=event)
    utils.create_job(recipe=r3, event=event)
    job_groups = event.get_sorted_jobs()
    self.assertEqual(len(job_groups), 3)
    self.assertEqual(len(job_groups[0]), 1)
    self.assertEqual(len(job_groups[1]), 2)
    self.assertEqual(len(job_groups[2]), 1)

  def test_pullrequest(self):
    pr = utils.create_pr()
    self.assertTrue(isinstance(pr, models.PullRequest))
    self.assertIn(pr.title, pr.__unicode__())
    self.assertNotEqual(pr.status_slug(), None)

  def test_buildconfig(self):
    bc = utils.create_build_config()
    self.assertTrue(isinstance(bc, models.BuildConfig))
    self.assertIn(bc.name, bc.__unicode__())

  def test_recipe(self):
    rc = utils.create_recipe()
    self.assertTrue(isinstance(rc, models.Recipe))
    self.assertIn(rc.name, rc.__unicode__())

    self.assertEqual(rc.auto_str(), models.Recipe.AUTO_CHOICES[rc.automatic][1])
    self.assertEqual(rc.cause_str(), models.Recipe.CAUSE_CHOICES[rc.cause][1])
    self.assertTrue(isinstance(rc.configs_str(), basestring))

    rc.cause = models.Recipe.CAUSE_PUSH
    rc.branch = utils.create_branch()
    rc.save()
    self.assertIn('Push', rc.cause_str())

    utils.create_recipe_dependency(recipe=rc)
    self.assertEqual(rc.depends_on.first().display_name, rc.dependency_str())

  def dependency_str(self):
    return ', '.join([ dep.display_name for dep in self.depends_on.all() ])

  def test_recipeenv(self):
    renv = utils.create_recipe_environment()
    self.assertTrue(isinstance(renv, models.RecipeEnvironment))
    self.assertIn(renv.name, renv.__unicode__())
    self.assertIn(renv.value, renv.__unicode__())

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
    self.assertNotEqual(c.status_str(), '')

  def test_job(self):
    j = utils.create_job()
    j.status = models.JobStatus.NOT_STARTED
    j.save()
    self.assertTrue(isinstance(j, models.Job))
    self.assertIn(j.recipe.name, j.__unicode__())
    self.assertEqual(j.status_slug(), 'Not_Started')
    self.assertEqual(j.status_str(), 'Not started')
    self.assertEqual(j.active_results().count(), 0)
    j.status = models.JobStatus.FAILED
    j.save()
    result = utils.create_step_result(job=j)
    self.assertEqual(None, j.failed_result())

    result.status = models.JobStatus.FAILED
    result.save()
    self.assertEqual(result, j.failed_result())

    result.status = models.JobStatus.FAILED_OK
    result.save()
    self.assertEqual(result, j.failed_result())

  def test_stepresult(self):
    sr = utils.create_step_result()
    sr.output = '&<\n\33[30mfoo\33[0m'
    self.assertTrue(isinstance(sr, models.StepResult))
    self.assertIn(sr.name, sr.__unicode__())
    self.assertEqual(models.JobStatus.to_slug(sr.status), sr.status_slug())
    self.assertEqual(sr.clean_output(), '&amp;&lt;<br/><span class="term-fg30">foo</span>')

  def test_generate_build_key(self):
    build_key = models.generate_build_key()
    self.assertNotEqual('', build_key)

  def test_jobstatus(self):
    for i in models.JobStatus.STATUS_CHOICES:
        self.assertEqual(models.JobStatus.to_str(i[0]), i[1])
    for i in models.JobStatus.SHORT_CHOICES:
        self.assertEqual(models.JobStatus.to_slug(i[0]), i[1])
