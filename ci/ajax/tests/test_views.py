from django.test import TestCase, Client
from django.test.client import RequestFactory
from django.core.urlresolvers import reverse
from django.conf import settings
from ci.tests import utils
from mock import patch
from ci.github import api
import shutil
import json

class ViewsTestCase(TestCase):
  fixtures = ['base']

  def setUp(self):
    self.client = Client()
    self.factory = RequestFactory()
    self.recipe_dir, self.repo = utils.create_recipe_dir()
    settings.RECIPE_BASE_DIR = self.recipe_dir

  def tearDown(self):
    shutil.rmtree(self.recipe_dir)

  def test_get_file(self):
    url = reverse('ci:ajax:get_file')
    # no parameters
    response = self.client.get(url)
    self.assertEqual(response.status_code, 400)

    data = {'user': 'no_user', 'filename': 'common/1.sh'}
    # not allowed
    response = self.client.get(url, data)
    self.assertEqual(response.status_code, 403)

    user = utils.get_test_user()
    utils.simulate_login(self.client.session, user)
    # should be ok
    data['user'] = user.name
    response = self.client.get(url, data)
    self.assertEqual(response.status_code, 200)
    self.assertIn('1.sh', response.content)

    #not found
    data['filename'] = 'common/no_exist'
    response = self.client.get(url, data)
    self.assertEqual(response.status_code, 400)

    #bad filename
    data['filename'] = '../no_exist'
    response = self.client.get(url, data)
    self.assertEqual(response.status_code, 400)

  @patch.object(api.GitHubAPI, 'is_collaborator')
  def test_get_result_output(self, mock_is_collaborator):
    mock_is_collaborator.return_value = False
    url = reverse('ci:ajax:get_result_output')
    # no parameters
    response = self.client.get(url)
    self.assertEqual(response.status_code, 400)

    result = utils.create_step_result()
    result.output = 'output'
    result.save()
    result.step.recipe.private = False
    result.step.recipe.save()
    data = {'result_id': result.pk}

    # should be ok since recipe isn't private
    response = self.client.get(url, data)
    self.assertEqual(response.status_code, 200)
    self.assertIn(result.output, response.content)

    result.step.recipe.private = True
    result.step.recipe.save()

    # recipe is private, shouldn't see it
    response = self.client.get(url, data)
    self.assertEqual(response.status_code, 403)

    user = utils.get_test_user()
    utils.simulate_login(self.client.session, user)
    # recipe is private, not a collaborator
    response = self.client.get(url, data)
    self.assertEqual(response.status_code, 403)

    mock_is_collaborator.return_value = True
    # recipe is private, but a collaborator
    response = self.client.get(url, data)
    self.assertEqual(response.status_code, 200)
    self.assertIn(result.output, response.content)

  def test_job_update(self):
    url = reverse('ci:ajax:job_update')
    # no parameters
    response = self.client.get(url)
    self.assertEqual(response.status_code, 400)

    job = utils.create_job()
    data = {'last_request': 10, 'limit': 10}

    response = self.client.get(url, data)
    self.assertEqual(response.status_code, 200)
    self.assertIn('jobs', response.content)
    json_data = json.loads(response.content)
    self.assertIn('jobs', json_data.keys())
    self.assertEqual(job.pk, json_data['jobs'][0]['id'])

  def test_status_update(self):
    url = reverse('ci:ajax:status_update')
    # no parameters
    response = self.client.get(url)
    self.assertEqual(response.status_code, 400)

    pr_open = utils.create_pr(title='open_pr', number=1)
    ev_open = utils.create_event()
    pr_open.closed = False
    pr_open.save()
    ev_open.pull_request = pr_open
    ev_open.save()
    pr_closed = utils.create_pr(title='closed_pr', number=2)
    pr_closed.closed = True
    pr_closed.save()
    ev_closed = utils.create_event(commit1='2345')
    ev_closed.pull_request = pr_closed
    ev_closed.save()

    data = {'last_request': 10}
    response = self.client.get(url, data)
    self.assertEqual(response.status_code, 200)
    json_data = json.loads(response.content)
    self.assertIn('repo_status', json_data.keys())
    self.assertIn('closed', json_data.keys())
    self.assertEqual(pr_open.title, json_data['repo_status'][0]['prs'][0]['title'])
    self.assertEqual(pr_closed.pk, json_data['closed'][0]['id'])

  @patch.object(api.GitHubAPI, 'is_collaborator')
  def test_job_results(self, mock_is_collaborator):
    mock_is_collaborator.return_value = False
    url = reverse('ci:ajax:job_results')
    # no parameters
    response = self.client.get(url)
    self.assertEqual(response.status_code, 400)

    step_result = utils.create_step_result()
    step_result.complete = True
    step_result.save()

    data = {'last_request': 10, 'job_id': step_result.job.pk }
    # not signed in, not a collaborator
    response = self.client.get(url, data)
    self.assertEqual(response.status_code, 403)

    user = utils.get_test_user()
    utils.simulate_login(self.client.session, user)
    mock_is_collaborator.return_value = True

    # should work now
    response = self.client.get(url, data)
    self.assertEqual(response.status_code, 200)
    json_data = json.loads(response.content)
    self.assertIn('job_info', json_data.keys())
    self.assertIn('results', json_data.keys())
    self.assertEqual(step_result.job.pk, json_data['job_info']['id'])
    self.assertEqual(step_result.pk, json_data['results'][0]['id'])

    # should work now but return no results
    data['last_request'] = -10
    response = self.client.get(url, data)
    self.assertEqual(response.status_code, 200)
    json_data = json.loads(response.content)
    self.assertIn('job_info', json_data.keys())
    self.assertIn('results', json_data.keys())
    self.assertEqual('', json_data['job_info'])
    self.assertEqual([], json_data['results'])
