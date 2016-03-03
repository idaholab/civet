from django.test import TestCase, RequestFactory, Client
from django.core.urlresolvers import reverse
from ci import models
from ci.tests import utils
from os import path
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
    url = reverse('ci:github:webhook', args=[10000])
    # only post allowed
    response = self.client.get(url)
    self.assertEqual(response.status_code, 405) # not allowed

    # no user
    response = self.client.post(url)
    self.assertEqual(response.status_code, 400)

    # no json
    user = utils.get_test_user()
    url = reverse('ci:github:webhook', args=[user.build_key])
    data = {'key': 'value'}
    response = self.client.post(url, data)
    self.assertEqual(response.status_code, 400)

    # bad json
    user = utils.get_test_user()
    url = reverse('ci:github:webhook', args=[user.build_key])
    response = self.client_post_json(url, data)
    self.assertEqual(response.status_code, 400)

  def test_pull_request(self):
    user = utils.get_test_user()
    repo = utils.create_repo(user=user)
    recipe = utils.create_recipe(user=user, repo=repo)
    recipe.cause = models.Recipe.CAUSE_PULL_REQUEST
    recipe.save()
    url = reverse('ci:github:webhook', args=[user.build_key])
    data = self.get_data('pr_open_01.json')
    py_data = json.loads(data)
    py_data['pull_request']['base']['repo']['owner']['login'] = user.name
    py_data['pull_request']['base']['repo']['name'] = repo.name
    py_data['pull_request']['title'] = '[WIP] testTitle'

    # no events or jobs on a work in progress
    jobs_before = models.Job.objects.filter(ready=True).count()
    events_before = models.Event.objects.count()

    response = self.client_post_json(url, py_data)
    self.assertEqual(response.status_code, 200)

    jobs_after = models.Job.objects.filter(ready=True).count()
    events_after = models.Event.objects.count()
    self.assertEqual(jobs_before, jobs_after)
    self.assertEqual(events_before, events_after)

    # no events or jobs on a work in progress
    py_data['pull_request']['title'] = 'WIP: testTitle'
    response = self.client_post_json(url, py_data)
    self.assertEqual(response.status_code, 200)
    jobs_after = models.Job.objects.filter(ready=True).count()
    events_after = models.Event.objects.count()
    self.assertEqual(jobs_before, jobs_after)
    self.assertEqual(events_before, events_after)

    # should produce a job and an event
    py_data['pull_request']['title'] = 'testTitle'
    response = self.client_post_json(url, py_data)
    self.assertEqual(response.status_code, 200)
    jobs_after = models.Job.objects.filter(ready=True).count()
    events_after = models.Event.objects.count()
    self.assertEqual(jobs_before+1, jobs_after)
    self.assertEqual(events_before+1, events_after)
    ev = models.Event.objects.latest()
    self.assertEqual(ev.trigger_user, py_data['pull_request']['user']['login'])

    # should just close the event
    py_data['action'] = 'closed'
    response = self.client_post_json(url, py_data)
    self.assertEqual(response.status_code, 200)
    jobs_after = models.Job.objects.filter(ready=True).count()
    events_after = models.Event.objects.count()
    self.assertEqual(jobs_before+1, jobs_after)
    self.assertEqual(events_before+1, events_after)
    ev = models.Event.objects.latest()
    self.assertTrue(ev.pull_request.closed)

    # should just open the same event
    py_data['action'] = 'reopened'
    response = self.client_post_json(url, py_data)
    self.assertEqual(response.status_code, 200)
    jobs_after = models.Job.objects.filter(ready=True).count()
    events_after = models.Event.objects.count()
    self.assertEqual(jobs_before+1, jobs_after)
    self.assertEqual(events_before+1, events_after)
    ev = models.Event.objects.latest()
    self.assertFalse(ev.pull_request.closed)

    py_data['action'] = 'labeled'
    response = self.client_post_json(url, py_data)
    self.assertEqual(response.status_code, 200)

    py_data['action'] = 'bad_action'
    response = self.client_post_json(url, py_data)
    self.assertEqual(response.status_code, 400)

  def test_push(self):
    user = utils.get_test_user()
    repo = utils.create_repo(user=user)
    branch = utils.create_branch(repo=repo)
    recipe = utils.create_recipe(user=user, repo=repo)
    recipe.cause = models.Recipe.CAUSE_PUSH
    recipe.branch = branch
    recipe.save()
    url = reverse('ci:github:webhook', args=[user.build_key])
    data = self.get_data('push_01.json')
    py_data = json.loads(data)
    py_data['repository']['owner']['name'] = user.name
    py_data['repository']['name'] = repo.name
    py_data['ref'] = 'refs/heads/{}'.format(branch.name)
    events_before = models.Event.objects.count()
    response = self.client_post_json(url, py_data)
    self.assertEqual(response.status_code, 200)
    events_after = models.Event.objects.count()
    self.assertEqual(events_before+1, events_after)
    ev = models.Event.objects.latest()
    self.assertEqual(ev.cause, models.Event.PUSH)
    self.assertEqual(ev.description, "Update README.md")

    py_data['head_commit']['message'] = "Merge commit '123456789'"
    py_data['after'] = '123456789'
    py_data['before'] = '1'
    events_before = models.Event.objects.count()
    response = self.client_post_json(url, py_data)
    self.assertEqual(response.status_code, 200)
    events_after = models.Event.objects.count()
    self.assertEqual(events_before+1, events_after)
    ev = models.Event.objects.latest()
    self.assertEqual(ev.description, "Merge commit 123456")

  def test_zen(self):
    user = utils.get_test_user()
    url = reverse('ci:github:webhook', args=[user.build_key])
    data = self.get_data('ping.json')
    py_data = json.loads(data)
    response = self.client_post_json(url, py_data)
    self.assertEqual(response.status_code, 200)
