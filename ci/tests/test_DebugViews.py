from django.core.urlresolvers import reverse
from django.conf import settings
from mock import patch
from . import utils
from ci.github import api
import DBTester

class Tests(DBTester.DBTester):
  def setUp(self):
    super(Tests, self).setUp()
    self.old_servers = settings.INSTALLED_GITSERVERS
    settings.INSTALLED_GITSERVERS = [settings.GITSERVER_GITHUB]
    self.create_default_recipes()

  def tearDown(self):
    super(Tests, self).tearDown()
    settings.INSTALLED_GITSERVERS = self.old_servers

  def test_start_session(self):
    settings.DEBUG = True
    response = self.client.get(reverse('ci:start_session', args=[1000]))
    self.assertEqual(response.status_code, 404)

    user = utils.get_test_user()
    owner = utils.get_owner()
    response = self.client.get(reverse('ci:start_session', args=[owner.pk]))
    # owner doesn't have a token
    self.assertEqual(response.status_code, 404)

    response = self.client.get(reverse('ci:start_session', args=[user.pk]))
    self.assertEqual(response.status_code, 302)
    self.assertIn('github_user', self.client.session)
    self.assertIn('github_token', self.client.session)

    settings.DEBUG = False
    response = self.client.get(reverse('ci:start_session', args=[user.pk]))
    self.assertEqual(response.status_code, 404)

  def test_start_session_by_name(self):
    settings.DEBUG = True

    # invalid name
    response = self.client.get(reverse('ci:start_session_by_name', args=['nobody']))
    self.assertEqual(response.status_code, 404)

    user = utils.get_test_user()
    owner = utils.get_owner()
    # owner doesn't have a token
    response = self.client.get(reverse('ci:start_session_by_name', args=[owner.name]))
    self.assertEqual(response.status_code, 404)

    # valid, user has a token
    response = self.client.get(reverse('ci:start_session_by_name', args=[user.name]))
    self.assertEqual(response.status_code, 302)
    self.assertIn('github_user', self.client.session)
    self.assertIn('github_token', self.client.session)

    settings.DEBUG = False
    response = self.client.get(reverse('ci:start_session_by_name', args=[user.name]))
    self.assertEqual(response.status_code, 404)

  @patch.object(api.GitHubAPI, 'is_collaborator')
  def test_job_script(self, mock_collab):
    # bad pk
    mock_collab.return_value = False
    response = self.client.get(reverse('ci:job_script', args=[1000]))
    self.assertEqual(response.status_code, 404)

    user = utils.get_test_user()
    job = utils.create_job(user=user)
    job.recipe.build_user = user
    job.recipe.save()
    utils.create_prestepsource(recipe=job.recipe)
    utils.create_recipe_environment(recipe=job.recipe)
    step = utils.create_step(recipe=job.recipe, filename='scripts/1.sh')
    utils.create_step_environment(step=step)

    url = reverse('ci:job_script', args=[job.pk])
    response = self.client.get(url)
    # owner doesn't have permission
    self.assertEqual(response.status_code, 404)

    mock_collab.return_value = True
    utils.simulate_login(self.client.session, user)
    response = self.client.get(url)
    self.assertEqual(response.status_code, 200)
    self.assertIn(job.recipe.name, response.content)
