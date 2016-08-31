
# Copyright 2016 Battelle Energy Alliance, LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from django.conf import settings
from django.core.urlresolvers import reverse
from mock import patch
from ci import models
from ci.tests import utils as test_utils
import os, json
from ci.gitlab import api, views
from ci.tests import DBTester

class Tests(DBTester.DBTester):
  def setUp(self):
    self.old_hostname = settings.GITLAB_HOSTNAME
    settings.GITLAB_HOSTNAME = "gitlab.com"
    self.old_installed = settings.INSTALLED_GITSERVERS
    settings.INSTALLED_GITSERVERS = [settings.GITSERVER_GITLAB]
    super(Tests, self).setUp()
    self.create_default_recipes(server_type=settings.GITSERVER_GITLAB)

  def tearDown(self):
    super(Tests, self).tearDown()
    settings.GITLAB_HOSTNAME = self.old_hostname
    settings.INSTALLED_GITSERVERS = self.old_installed

  def get_data(self, fname):
    p = '{}/{}'.format(os.path.dirname(__file__), fname)
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
    user = test_utils.get_test_user()
    url = reverse('ci:gitlab:webhook', args=[user.build_key])
    data = {'key': 'value'}
    response = self.client.post(url, data)
    self.assertEqual(response.status_code, 400)

    # bad json
    user = test_utils.get_test_user()
    url = reverse('ci:gitlab:webhook', args=[user.build_key])
    response = self.client_post_json(url, data)
    self.assertEqual(response.status_code, 400)

  class PrResponse(object):
    def __init__(self, user, repo, title='testTitle', error=None):
      """
      All the responses all in one dict
      """
      self.data = {'title': title,
          'path_with_namespace': '{}/{}'.format(user.name, repo.name),
          'iid': '1',
          'owner': {'username': user.name},
          'name': repo.name,
          'commit': {'id': '1'},
          'ssh_url_to_repo': 'testUrl',
          }
      if error:
        self.data["message"] = error

    def json(self):
      return self.data

  def test_close_pr(self):
    user = test_utils.get_test_user()
    repo = test_utils.create_repo(user=user)
    pr = test_utils.create_pr(repo=repo, number=1)
    pr.closed = False
    pr.save()
    views.close_pr('foo', 'bar', 1, user.server)
    pr.refresh_from_db()
    self.assertFalse(pr.closed)

    views.close_pr(user.name, 'bar', 1, user.server)
    pr.refresh_from_db()
    self.assertFalse(pr.closed)

    views.close_pr(user.name, repo.name, 0, user.server)
    pr.refresh_from_db()
    self.assertFalse(pr.closed)

    views.close_pr(user.name, repo.name, 1, user.server)
    pr.refresh_from_db()
    self.assertTrue(pr.closed)

  @patch.object(api.GitLabAPI, 'get')
  def test_pull_request_bad_source(self, mock_get):
    """
    Sometimes the user hasn't given moosetest access to their repository
    and an error occurs. It is hard to check if a successful comment
    has happened but just try to get coverage.
    """
    data = self.get_data('pr_open_01.json')
    pr_data = json.loads(data)

    # Simulate an error on the server while getting the source branch
    mock_get.return_value = self.PrResponse(self.owner, self.repo, error="Error occurred")
    url = reverse('ci:gitlab:webhook', args=[self.build_user.build_key])

    self.set_counts()
    response = self.client_post_json(url, pr_data)
    self.assertEqual(response.status_code, 400)
    self.compare_counts()

  @patch.object(api.GitLabAPI, 'get')
  def test_pull_request(self, mock_get):
    """
    Unlike with GitHub, GitLab requires that you
    do a bunch of extra requests to get the needed information.
    Since we don't have authorization we have to mock these up.
    """
    data = self.get_data('pr_open_01.json')
    pr_data = json.loads(data)

    # no recipe so no jobs so no event should be created
    mock_get.return_value = self.PrResponse(self.owner, self.repo)
    url = reverse('ci:gitlab:webhook', args=[self.build_user.build_key])

    self.set_counts()
    response = self.client_post_json(url, pr_data)
    self.assertEqual(response.status_code, 200)
    self.compare_counts()

    pr_data['object_attributes']['target']['namespace'] = self.owner.name
    pr_data['object_attributes']['target']['name'] = self.repo.name

    # there is a recipe but the PR is a work in progress
    title = '[WIP] testTitle'
    pr_data['object_attributes']['title'] = title
    mock_get.return_value = self.PrResponse(self.owner, self.repo, title=title)
    self.set_counts()
    response = self.client_post_json(url, pr_data)
    self.assertEqual(response.status_code, 200)
    self.compare_counts()

    # there is a recipe but the PR is a work in progress
    title = 'WIP: testTitle'
    pr_data['object_attributes']['title'] = title
    mock_get.return_value = self.PrResponse(self.owner, self.repo, title=title)
    self.set_counts()
    response = self.client_post_json(url, pr_data)
    self.assertEqual(response.status_code, 200)
    self.compare_counts()

    # there is a recipe so a job should be made ready
    title = 'testTitle'
    pr_data['object_attributes']['title'] = title
    mock_get.return_value = self.PrResponse(self.owner, self.repo, title=title)
    self.set_counts()
    response = self.client_post_json(url, pr_data)
    self.assertEqual(response.status_code, 200)

    self.compare_counts(jobs=2, ready=1, events=1, users=1, repos=1, branches=2, commits=2, prs=1, active=2, active_repos=1)
    ev = models.Event.objects.latest()
    self.assertEqual(ev.jobs.first().ready, True)
    self.assertEqual(ev.pull_request.title, 'testTitle')
    self.assertEqual(ev.pull_request.closed, False)
    self.assertEqual(ev.trigger_user, pr_data['user']['username'])

    pr_data['object_attributes']['state'] = 'closed'
    self.set_counts()
    response = self.client_post_json(url, pr_data)
    self.assertEqual(response.status_code, 200)
    self.compare_counts(pr_closed=True)

    pr_data['object_attributes']['state'] = 'reopened'
    self.set_counts()
    response = self.client_post_json(url, pr_data)
    self.assertEqual(response.status_code, 200)
    self.compare_counts(pr_closed=False)

    pr_data['object_attributes']['state'] = 'synchronize'
    self.set_counts()
    response = self.client_post_json(url, pr_data)
    self.assertEqual(response.status_code, 200)
    self.compare_counts()

    pr_data['object_attributes']['state'] = 'merged'
    self.set_counts()
    response = self.client_post_json(url, pr_data)
    self.assertEqual(response.status_code, 200)
    self.compare_counts(pr_closed=True)

    pr_data['object_attributes']['state'] = 'unknown'
    self.set_counts()
    response = self.client_post_json(url, pr_data)
    self.assertEqual(response.status_code, 400)
    self.compare_counts(pr_closed=True)

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
    """
    The push event for GitLab just gives project ids and user ids
    which isn't enough information.
    It does an additional request to get more information about
    the project.
    """
    data = self.get_data('push_01.json')
    push_data = json.loads(data)

    # no recipe so no jobs should be created
    self.set_counts()
    mock_get.return_value = self.PushResponse(self.owner, self.repo)
    url = reverse('ci:gitlab:webhook', args=[self.build_user.build_key])
    response = self.client_post_json(url, push_data)
    self.assertEqual(response.status_code, 200)
    self.compare_counts()

    push_data['ref'] = "refs/heads/%s" % self.branch.name

    self.set_counts()
    response = self.client_post_json(url, push_data)
    self.assertEqual(response.status_code, 200)
    self.compare_counts(jobs=2, ready=1, events=1, commits=2, active=2, active_repos=1)
