from django.core.urlresolvers import reverse
from ci import models
from ci.tests import utils as test_utils
from os import path
from requests_oauthlib import OAuth2Session
from mock import patch
import json
from django.conf import settings
from ci.tests import DBTester

class GitHubViewsTests(DBTester.DBTester):
  def setUp(self):
    super(GitHubViewsTests, self).setUp()
    self.create_default_recipes()

  def get_data(self, fname):
    p = '{}/{}'.format(path.dirname(__file__), fname)
    with open(p, 'r') as f:
      contents = f.read()
      return contents

  def client_post_json(self, url, data):
    json_data = json.dumps(data)
    return self.client.post(url, json_data, content_type='application/json')

  def test_webhook(self):
    url = reverse('ci:github:webhook', args=[10000])
    # only post allowed
    response = self.client.get(url)
    self.assertEqual(response.status_code, 405) # not allowed

    # no user
    response = self.client.post(url)
    self.assertEqual(response.status_code, 400)

    # no json
    user = test_utils.get_test_user()
    url = reverse('ci:github:webhook', args=[user.build_key])
    data = {'key': 'value'}
    response = self.client.post(url, data)
    self.assertEqual(response.status_code, 400)

    # bad json
    user = test_utils.get_test_user()
    url = reverse('ci:github:webhook', args=[user.build_key])
    response = self.client_post_json(url, data)
    self.assertEqual(response.status_code, 400)

  @patch.object(OAuth2Session, 'delete')
  def test_pull_request(self, mock_del):
    url = reverse('ci:github:webhook', args=[self.build_user.build_key])
    data = self.get_data('pr_open_01.json')
    py_data = json.loads(data)
    py_data['pull_request']['base']['repo']['owner']['login'] = self.owner.name
    py_data['pull_request']['base']['repo']['name'] = self.repo.name
    py_data['pull_request']['title'] = '[WIP] testTitle'

    # no events or jobs on a work in progress
    self.set_counts()
    response = self.client_post_json(url, py_data)
    self.assertEqual(response.status_code, 200)
    self.compare_counts()

    # no events or jobs on a work in progress
    py_data['pull_request']['title'] = 'WIP: testTitle'
    self.set_counts()
    response = self.client_post_json(url, py_data)
    self.assertEqual(response.status_code, 200)
    self.compare_counts()

    # should produce a job and an event
    py_data['pull_request']['title'] = 'testTitle'
    self.set_counts()
    response = self.client_post_json(url, py_data)
    self.assertEqual(response.status_code, 200)
    self.compare_counts(jobs=2, ready=1, events=1, commits=2, users=1, repos=1, branches=1, prs=1, active=2)
    ev = models.Event.objects.latest()
    self.assertEqual(ev.trigger_user, py_data['pull_request']['user']['login'])

    # should just close the event
    py_data['action'] = 'closed'
    self.set_counts()
    response = self.client_post_json(url, py_data)
    self.assertEqual(response.status_code, 200)
    self.compare_counts(pr_closed=True)

    # should just open the same event
    py_data['action'] = 'reopened'
    self.set_counts()
    response = self.client_post_json(url, py_data)
    self.assertEqual(response.status_code, 200)
    self.compare_counts()

    # nothing should change
    py_data['action'] = 'labeled'
    self.set_counts()
    response = self.client_post_json(url, py_data)
    self.assertEqual(response.status_code, 200)
    self.compare_counts()

    # nothing should change
    py_data['action'] = 'bad_action'
    self.set_counts()
    response = self.client_post_json(url, py_data)
    self.assertEqual(response.status_code, 400)
    self.compare_counts()

    # on synchronize we also remove labels on the PR
    py_data['action'] = 'synchronize'
    settings.REMOTE_UPDATE = True
    mock_del.return_value = test_utils.Response()
    response = self.client_post_json(url, py_data)
    settings.REMOTE_UPDATE = False
    self.assertEqual(response.status_code, 200)

  def test_push(self):
    url = reverse('ci:github:webhook', args=[self.build_user.build_key])
    data = self.get_data('push_01.json')
    py_data = json.loads(data)
    py_data['repository']['owner']['name'] = self.owner.name
    py_data['repository']['name'] = self.repo.name
    py_data['ref'] = 'refs/heads/{}'.format(self.branch.name)

    # Everything OK
    self.set_counts()
    response = self.client_post_json(url, py_data)
    self.assertEqual(response.status_code, 200)
    self.compare_counts(jobs=2, ready=1, events=1, commits=2, active=2)
    ev = models.Event.objects.latest()
    self.assertEqual(ev.cause, models.Event.PUSH)
    self.assertEqual(ev.description, "Update README.md")

    py_data['head_commit']['message'] = "Merge commit '123456789'"
    py_data['after'] = '123456789'
    py_data['before'] = '1'
    self.set_counts()
    response = self.client_post_json(url, py_data)
    self.assertEqual(response.status_code, 200)
    self.compare_counts(jobs=2, ready=1, events=1, commits=2, active=2)
    ev = models.Event.objects.latest()
    self.assertEqual(ev.description, "Merge commit 123456")

  def test_zen(self):
    url = reverse('ci:github:webhook', args=[self.build_user.build_key])
    data = self.get_data('ping.json')
    py_data = json.loads(data)
    response = self.client_post_json(url, py_data)
    self.set_counts()
    self.assertEqual(response.status_code, 200)
    self.compare_counts()
