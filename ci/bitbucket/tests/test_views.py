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
    url = reverse('ci:bitbucket:webhook', args=[10000])
    # only post allowed
    response = self.client.get(url)
    self.assertEqual(response.status_code, 405) # not allowed

    # no user
    response = self.client.post(url)
    self.assertEqual(response.status_code, 400)

    # no json
    user = utils.get_test_user()
    url = reverse('ci:bitbucket:webhook', args=[user.build_key])
    data = {'key': 'value'}
    response = self.client.post(url, data)
    self.assertEqual(response.status_code, 400)

    # bad json
    user = utils.get_test_user()
    url = reverse('ci:bitbucket:webhook', args=[user.build_key])
    response = self.client_post_json(url, data)
    self.assertEqual(response.status_code, 400)

  def test_pull_request(self):
    # FIXME: Need to get some sample data to load
    user = utils.get_test_user()
    repo = utils.create_repo(user=user)
    recipe = utils.create_recipe(user=user, repo=repo)
    recipe.cause = models.Recipe.CAUSE_PULL_REQUEST
    recipe.save()
    #url = reverse('ci:bitbucket:webhook', args=[user.build_key])

  def test_push(self):
    # FIXME: Need to get some sample data to load
    user = utils.get_test_user()
    repo = utils.create_repo(user=user)
    branch = utils.create_branch(repo=repo)
    recipe = utils.create_recipe(user=user, repo=repo)
    recipe.cause = models.Recipe.CAUSE_PUSH
    recipe.branch = branch
    recipe.save()
    #url = reverse('ci:bitbucket:webhook', args=[user.build_key])
