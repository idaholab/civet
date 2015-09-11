from django.test import TestCase, RequestFactory, Client
from django.core.urlresolvers import reverse
from mock import patch
from ci import models
from ci.tests import utils
from os import path
from ci.gitlab import api
import json

class ViewsTestCase(TestCase):
  fixtures = ['base']

  def setUp(self):
    self.client = Client()
    self.factory = RequestFactory()

  def get_data(self, fname):
    p = '{}/{}'.format(path.dirname(__file__), fname)
    with open(p, 'r') as f:
      contents = f.read()
      return contents

  def client_post_json(self, url, data):
    json_data = json.dumps(data)
    return self.client.post(url, json_data, content_type='application/json')

  def test_webhook(self):
    url = reverse('ci:gitlab:webhook', args=[10000])
    # only post allowed
    response = self.client.get(url)
    self.assertEqual(response.status_code, 405) # not allowed

    # no user
    response = self.client.post(url)
    self.assertEqual(response.status_code, 400)

    # no json
    user = utils.get_test_user()
    url = reverse('ci:gitlab:webhook', args=[user.build_key])
    data = {'key': 'value'}
    response = self.client.post(url, data)
    self.assertEqual(response.status_code, 400)

    # bad json
    user = utils.get_test_user()
    url = reverse('ci:gitlab:webhook', args=[user.build_key])
    response = self.client_post_json(url, data)
    self.assertEqual(response.status_code, 400)

  class PrResponse(object):
    def __init__(self, user, repo):
      """
      All the responses all in one dict
      """
      self.data = {'title': 'testTitle',
          'path_with_namespace': '{}/{}'.format(user.name, repo.name),
          'iid': '1',
          'owner': {'username': user.name},
          'name': repo.name,
          'commit': {'id': '1'},
          'ssh_url_to_repo': 'testUrl',
          }

    def json(self):
      return self.data

  @patch.object(api.GitLabAPI, 'get')
  def test_pull_request(self, mock_get):
    """
    Unlike with GitHub, GitLab requires that you
    do a bunch of extra requests to get the needed information.
    Since we don't have authorization we have to mock these
    up.
    """
    data = self.get_data('pr_open_01.json')
    pr_data = json.loads(data)
    user = utils.create_user_with_token(name='testmb')
    repo = utils.create_repo(user=user, name='test_repo')

    jobs_before = models.Job.objects.filter(ready=True).count()
    events_before = models.Event.objects.count()

    # no recipe so no jobs so no event should be created
    mock_get.return_value = self.PrResponse(user, repo)
    url = reverse('ci:gitlab:webhook', args=[user.build_key])

    response = self.client_post_json(url, pr_data)
    self.assertEqual(response.status_code, 200)
    jobs_after = models.Job.objects.filter(ready=True).count()
    events_after = models.Event.objects.count()
    self.assertEqual(jobs_before, jobs_after)
    self.assertEqual(events_before, events_after)

    # there is a recipe so a job should be made ready
    recipe = utils.create_recipe(repo=repo)
    recipe.cause = models.Recipe.CAUSE_PULL_REQUEST
    recipe.save()
    response = self.client_post_json(url, pr_data)
    self.assertEqual(response.status_code, 200)
    jobs_after = models.Job.objects.filter(ready=True).count()
    events_after = models.Event.objects.count()
    self.assertEqual(jobs_before+1, jobs_after)
    self.assertEqual(events_before+1, events_after)
    ev = models.Event.objects.latest()
    self.assertEqual(ev.jobs.first().ready, True)
    self.assertEqual(ev.pull_request.title, 'testTitle')
    self.assertEqual(ev.pull_request.closed, False)

    pr_data['object_attributes']['state'] = 'closed'
    response = self.client_post_json(url, pr_data)
    self.assertEqual(response.status_code, 200)
    ev = models.Event.objects.latest()
    self.assertEqual(ev.pull_request.closed, True)

    pr_data['object_attributes']['state'] = 'reopened'
    response = self.client_post_json(url, pr_data)
    self.assertEqual(response.status_code, 200)
    ev = models.Event.objects.latest()
    self.assertEqual(ev.pull_request.closed, False)

    pr_data['object_attributes']['state'] = 'synchronize'
    response = self.client_post_json(url, pr_data)
    self.assertEqual(response.status_code, 200)
    ev = models.Event.objects.latest()
    self.assertEqual(ev.pull_request.closed, False)

    pr_data['object_attributes']['state'] = 'merged'
    response = self.client_post_json(url, pr_data)
    self.assertEqual(response.status_code, 200)
    ev = models.Event.objects.latest()
    self.assertEqual(ev.pull_request.closed, True)


  class PushResponse(object):
    def __init__(self, user, repo):
      """
      All the responses all in one dict
      """
      self.data = {
          'name': repo.name,
          'namespace': {'name': user.name},
          }
    def json(self):
      return self.data

  @patch.object(api.GitLabAPI, 'get')
  def test_push(self, mock_get):
    data = self.get_data('push_01.json')
    push_data = json.loads(data)

    user = utils.create_user_with_token(name='testmb')
    repo = utils.create_repo(user=user, name='test_repo')

    jobs_before = models.Job.objects.filter(ready=True).count()
    events_before = models.Event.objects.count()

    # no recipe so no jobs should be created
    mock_get.return_value = self.PushResponse(user, repo)
    url = reverse('ci:gitlab:webhook', args=[user.build_key])
    response = self.client_post_json(url, push_data)
    self.assertEqual(response.status_code, 200)
    jobs_after = models.Job.objects.filter(ready=True).count()
    events_after = models.Event.objects.count()
    self.assertEqual(jobs_before, jobs_after)
    self.assertEqual(events_before, events_after)

    branch_name = push_data['ref'].split('/')[-1]
    branch = utils.create_branch(name=branch_name, repo=repo)
    recipe = utils.create_recipe(repo=repo)
    recipe.cause = models.Recipe.CAUSE_PUSH
    recipe.branch = branch
    recipe.save()

    response = self.client_post_json(url, push_data)
    self.assertEqual(response.status_code, 200)
    jobs_after = models.Job.objects.filter(ready=True).count()
    events_after = models.Event.objects.count()
    self.assertEqual(jobs_before+1, jobs_after)
    self.assertEqual(events_before+1, events_after)
