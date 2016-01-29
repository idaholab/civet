from django.test import TestCase, Client
from django.core.urlresolvers import reverse
from django.conf import settings
from django.test.client import RequestFactory
from ci import models
from ci.tests import utils
from ci.gitlab import api
from ci.git_api import GitException
from mock import patch
import requests
import os
from requests_oauthlib import OAuth2Session

class APITestCase(TestCase):
  fixtures = ['base.json',]

  def setUp(self):
    self.client = Client()
    self.factory = RequestFactory()
    self.server = models.GitServer.objects.filter(host_type=settings.GITSERVER_GITLAB).first()

  def get_json_file(self, filename):
    dirname, fname = os.path.split(os.path.abspath(__file__))
    with open(dirname + '/' + filename, 'r') as f:
      js = f.read()
      return js

  def test_webhook_pr(self):
    """
    pr_open_01: testmb01 opens pull request from testmb01/repo01:devel to testmb/repo01:devel
    """
    """
    test_user = utils.get_test_user()
    owner = utils.get_owner()
    jobs_before = models.Job.objects.filter(ready=True).count()
    events_before = models.Event.objects.count()

    t1 = self.get_json_file('pr_open_01.json')
    response = self.client.post(reverse('ci:gitlab:webhook', args=[test_user.build_key]), data=t1, content_type="application/json")
    self.assertEqual(response.content, "OK")

    # no recipes are there so no events/jobs should be created
    jobs_after = models.Job.objects.filter(ready=True).count()
    events_after = models.Event.objects.count()
    self.assertEqual(events_after, events_before)
    self.assertEqual(jobs_after, jobs_before)

    repo = utils.create_repo(name='repo01', user=owner)
    utils.create_recipe(user=test_user, repo=repo) # just create it so a job will get created

    response = self.client.post(reverse('ci:gitlab:webhook', args=[test_user.build_key]), data=t1, content_type="application/json")
    self.assertEqual(response.content, "OK")

    jobs_after = models.Job.objects.filter(ready=True).count()
    events_after = models.Event.objects.count()
    self.assertGreater(events_after, events_before)
    self.assertGreater(jobs_after, jobs_before)
  """
  pass

  def test_webhook_push(self):
    """
    pr_push_01.json: testmb01 push from testmb01/repo02:devel to testmb/repo02:devel
    """
    """
    test_user = utils.get_test_user()
    owner = utils.get_owner()
    jobs_before = models.Job.objects.filter(ready=True).count()
    events_before = models.Event.objects.count()

    t1 = self.get_json_file('push_01.json')
    response = self.client.post(reverse('ci:gitlab:webhook', args=[test_user.build_key]), data=t1, content_type="application/json")
    self.assertEqual(response.content, "OK")

    # no recipes are there so no events/jobs should be created
    jobs_after = models.Job.objects.filter(ready=True).count()
    events_after = models.Event.objects.count()
    self.assertEqual(events_after, events_before)
    self.assertEqual(jobs_after, jobs_before)

    repo = utils.create_repo(name='repo02', user=owner)
    branch = utils.create_branch(name='devel', repo=repo)
    utils.create_recipe(user=test_user, repo=repo, branch=branch, cause=models.Recipe.CAUSE_PUSH) # just create it so a job will get created

    response = self.client.post(reverse('ci:gitlab:webhook', args=[test_user.build_key]), data=t1, content_type="application/json")
    self.assertEqual(response.content, "OK")

    jobs_after = models.Job.objects.filter(ready=True).count()
    events_after = models.Event.objects.count()
    self.assertGreater(events_after, events_before)
    self.assertGreater(jobs_after, jobs_before)
    """
    pass

  class LinkResponse(object):
    def __init__(self, json_dict, use_links=False, status_code=200):
      if use_links:
        self.links = {'next': {'url': 'next_url'}}
      else:
        self.links = []
      self.json_dict = json_dict
      self.status_code = status_code

    def json(self):
      return self.json_dict

  @patch.object(api.GitLabAPI, 'get')
  def test_get_repos(self, mock_get):
    user = utils.create_user_with_token(server=self.server)
    utils.simulate_login(self.client.session, user)
    auth = user.server.auth().start_session_for_user(user)
    gapi = api.GitLabAPI()
    mock_get.return_value = self.LinkResponse([])
    repos = gapi.get_repos(auth, self.client.session)
    # shouldn't be any repos
    self.assertEqual(len(repos), 0)

    mock_get.return_value = self.LinkResponse([{'namespace': {'name':user.name}, 'name': 'repo2'}, {'namespace': {'name': user.name}, 'name': 'repo2'}])
    repos = gapi.get_repos(auth, self.client.session)
    self.assertEqual(len(repos), 2)

    session = self.client.session
    session['gitlab_repos'] = ['repo1']
    session.save()
    repos = gapi.get_repos(auth, self.client.session)
    self.assertEqual(len(repos), 1)
    self.assertEqual(repos[0], 'repo1')

  @patch.object(api.GitLabAPI, 'get')
  def test_get_org_repos(self, mock_get):
    user = utils.create_user_with_token(server=self.server)
    utils.simulate_login(self.client.session, user)
    auth = user.server.auth().start_session_for_user(user)
    gapi = api.GitLabAPI()
    mock_get.return_value = self.LinkResponse([])
    repos = gapi.get_org_repos(auth, self.client.session)
    # shouldn't be any repos
    self.assertEqual(len(repos), 0)

    mock_get.return_value = self.LinkResponse([{'namespace': {'name': 'name'}, 'name': 'repo2'}, {'namespace': {'name': 'name'}, 'name': 'repo2'}])
    repos = gapi.get_org_repos(auth, self.client.session)
    self.assertEqual(len(repos), 2)

    session = self.client.session
    session['gitlab_org_repos'] = ['newrepo1']
    session.save()
    repos = gapi.get_org_repos(auth, self.client.session)
    self.assertEqual(len(repos), 1)
    self.assertEqual(repos[0], 'newrepo1')

  @patch.object(api.GitLabAPI, 'get')
  def test_get_branches(self, mock_get):
    user = utils.create_user_with_token(server=self.server)
    repo = utils.create_repo(user=user)
    utils.simulate_login(self.client.session, user)
    auth = user.server.auth().start_session_for_user(user)
    gapi = api.GitLabAPI()
    mock_get.return_value = self.LinkResponse([])
    branches = gapi.get_branches(auth, user, repo)
    # shouldn't be any branch
    self.assertEqual(len(branches), 0)

    mock_get.return_value = self.LinkResponse([{'name': 'branch1'}, {'name': 'branch2'}])
    branches = gapi.get_branches(auth, user, repo)
    self.assertEqual(len(branches), 2)

  @patch.object(api.GitLabAPI, 'get')
  def test_get_group_id(self, mock_get):
    user = utils.create_user_with_token(server=self.server)
    token = user.token
    gapi = api.GitLabAPI()
    auth = user.server.auth().start_session_for_user(user)
    mock_get.return_value = self.LinkResponse([{'name': user.name, 'id': 42}])
    group_id = gapi.get_group_id(auth, token, user.name)
    self.assertEqual(group_id, 42)

  @patch.object(api.GitLabAPI, 'get')
  def test_is_group_member(self, mock_get):
    user = utils.create_user_with_token(server=self.server)
    token = user.token
    gapi = api.GitLabAPI()
    auth = user.server.auth().start_session_for_user(user)
    mock_get.return_value = self.LinkResponse([{'username': user.name}])
    ret = gapi.is_group_member(auth, token, 42, user.name)
    self.assertTrue(ret)
    mock_get.return_value = self.LinkResponse([])
    ret = gapi.is_group_member(auth, token, 42, user.name)
    self.assertFalse(ret)

  @patch.object(api.GitLabAPI, 'get')
  def test_is_collaborator(self, mock_get):
    user = utils.create_user_with_token(server=self.server)
    repo = utils.create_repo(user=user)
    gapi = api.GitLabAPI()
    utils.simulate_login(self.client.session, user)
    auth = user.server.auth().start_session_for_user(user)
    # user is repo owner
    self.assertTrue(gapi.is_collaborator(auth, user, repo))
    user2 = utils.create_user('user2', server=self.server)

    # a collaborator
    repo = utils.create_repo(user=user2)
    mock_get.return_value = self.LinkResponse([{'username': user.name}])
    self.assertTrue(gapi.is_collaborator(auth, user, repo))

    # not a collaborator
    mock_get.return_value = self.LinkResponse([{'username': 'none'}])
    self.assertFalse(gapi.is_collaborator(auth, user, repo))

  class ShaResponse(object):
    def __init__(self, commit=True):
      if commit:
        self.content = '{\n\t"commit": {\n\t\t"id": "123"\n\t}\n}'
      else:
        self.content = 'nothing'

  @patch.object(api.GitLabAPI, 'get')
  def test_last_sha(self, mock_get):
    user = utils.create_user_with_token(server=self.server)
    branch = utils.create_branch(user=user)
    gapi = api.GitLabAPI()
    utils.simulate_login(self.client.session, user)
    auth = user.server.auth().start_session_for_user(user)
    mock_get.return_value = self.ShaResponse(True)
    sha = gapi.last_sha(auth, user, branch.repository, branch)
    self.assertEqual(sha, '123')

    mock_get.return_value = self.ShaResponse(False)
    sha = gapi.last_sha(auth, user, branch.repository, branch)
    self.assertEqual(sha, None)

    mock_get.side_effect = Exception()
    sha = gapi.last_sha(auth, user, branch.repository, branch)
    self.assertEqual(sha, None)


  @patch.object(api.GitLabAPI, 'get')
  def test_get_all_pages(self, mock_get):
    user = utils.create_user_with_token(server=self.server)
    gapi = api.GitLabAPI()
    utils.simulate_login(self.client.session, user)
    auth = user.server.auth().start_session_for_user(user)
    init_response = self.LinkResponse([{'foo': 'bar'}], True)
    mock_get.return_value = self.LinkResponse([{'bar': 'foo'}], False)
    all_json = gapi.get_all_pages(auth, init_response)
    self.assertEqual(len(all_json), 2)
    self.assertIn('foo', all_json[0])
    self.assertIn('bar', all_json[1])

  @patch.object(api.GitLabAPI, 'get')
  @patch.object(api.GitLabAPI, 'post')
  def test_install_webhooks(self, mock_post, mock_get):
    user = utils.create_user_with_token(server=self.server)
    repo = utils.create_repo(user=user)
    gapi = api.GitLabAPI()
    utils.simulate_login(self.client.session, user)
    auth = user.server.auth().start_session_for_user(user)
    get_data = []
    request = self.factory.get('/')
    callback_url = request.build_absolute_uri(reverse('ci:gitlab:webhook', args=[user.build_key]))
    get_data.append({'merge_request_events': 'true', 'push_events': 'true', 'url': 'no_url'})
    mock_get.return_value = self.LinkResponse(get_data, False)
    mock_post.return_value = self.LinkResponse({'errors': 'error'}, False, 404)
    settings.INSTALL_WEBHOOK = True
    # with this data it should try to install the hook but there is an error
    with self.assertRaises(GitException):
      gapi.install_webhooks(request, auth, user, repo)

    # with this data it should do the hook
    mock_post.return_value = self.LinkResponse([], False)
    gapi.install_webhooks(request, auth, user, repo)

    # with this data the hook already exists
    get_data.append({'merge_request_events': 'true', 'push_events': 'true', 'url': callback_url })
    gapi.install_webhooks(request, auth, user, repo)

    settings.INSTALL_WEBHOOK = False
    # this should just return
    gapi.install_webhooks(request, auth, user, repo)

  @patch.object(requests, 'post')
  def test_post(self, mock_post):
    gapi = api.GitLabAPI()
    mock_post.return_value = '123'
    # should just return whatever requests.post returns
    self.assertEqual(gapi.post('url', 'token', {}), '123')

  @patch.object(requests, 'get')
  def test_get(self, mock_get):
    gapi = api.GitLabAPI()
    mock_get.return_value = '123'
    # should just return whatever requests.get returns
    self.assertEqual(gapi.get('url', 'token'), '123')

  @patch.object(api.GitLabAPI, 'post')
  def test_pr_comment(self, mock_post):
    # no real state that we can check, so just go for coverage
    settings.REMOTE_UPDATE = True
    mock_post.return_value = True
    gapi = api.GitLabAPI()
    user = utils.create_user_with_token(server=self.server)
    utils.simulate_login(self.client.session, user)
    auth = user.server.auth().start_session_for_user(user)
    # valid post
    gapi.pr_comment(auth, 'url', 'message')

    # bad post
    mock_post.side_effect = Exception()
    gapi.pr_comment(auth, 'url', 'message')

    settings.REMOTE_UPDATE = False
    # should just return
    gapi.pr_comment(auth, 'url', 'message')

  class PrResponse(object):
    def __init__(self, status_code, content):
      self.content = content
      self.status_code = status_code

  @patch.object(OAuth2Session, 'post')
  def test_update_pr_status(self, mock_post):
    user = utils.create_user_with_token()
    gapi = api.GitLabAPI()
    utils.simulate_login(self.client.session, user)
    auth = user.server.auth().start_session_for_user(user)
    ev = utils.create_event(user=user)
    pr = utils.create_pr()
    ev.pull_request = pr
    ev.save()
    # no state is set so just run for coverage
    settings.REMOTE_UPDATE = True
    mock_post.return_value = self.PrResponse(200, "some content")
    gapi.update_pr_status(auth, ev.base, ev.head, gapi.PENDING, 'event', 'desc', 'context')
    mock_post.return_value = self.PrResponse(404, 'nothing')
    gapi.update_pr_status(auth, ev.base, ev.head, gapi.PENDING, 'event', 'desc', 'context')
    mock_post.side_effect = Exception('exception')
    gapi.update_pr_status(auth, ev.base, ev.head, gapi.PENDING, 'event', 'desc', 'context')

    # This should just return
    settings.REMOTE_UPDATE = False
    gapi.update_pr_status(auth, ev.base, ev.head, gapi.PENDING, 'event', 'desc', 'context')

