from django.test import TestCase, Client
from django.core.urlresolvers import reverse
from django.test.client import RequestFactory
from requests_oauthlib import OAuth2Session
#from django.core.urlresolvers import reverse
from django.conf import settings
from ci import models
from ci.tests import utils
from ci.bitbucket import api
from ci.git_api import GitException
from mock import patch
import os

class APITestCase(TestCase):
  fixtures = ['base.json',]

  def setUp(self):
    self.client = Client()
    self.factory = RequestFactory()
    self.server = models.GitServer.objects.filter(host_type=settings.GITSERVER_BITBUCKET).first()

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
    response = self.client.post(reverse('ci:bitbucket:webhook', args=[test_user.build_key]), data=t1, content_type="application/json")
    self.assertEqual(response.content, "OK")

    # no recipes are there so no events/jobs should be created
    jobs_after = models.Job.objects.filter(ready=True).count()
    events_after = models.Event.objects.count()
    self.assertEqual(events_after, events_before)
    self.assertEqual(jobs_after, jobs_before)

    repo = utils.create_repo(name='repo01', user=owner)
    utils.create_recipe(user=test_user, repo=repo) # just create it so a job will get created

    response = self.client.post(reverse('ci:bitbucket:webhook', args=[test_user.build_key]), data=t1, content_type="application/json")
    self.assertEqual(response.content, "OK")

    jobs_after = models.Job.objects.filter(ready=True).count()
    events_after = models.Event.objects.count()
    self.assertGreater(events_after, events_before)
    self.assertGreater(jobs_after, jobs_before)
  """

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
    response = self.client.post(reverse('ci:bitbucket:webhook', args=[test_user.build_key]), data=t1, content_type="application/json")
    self.assertEqual(response.content, "OK")

    # no recipes are there so no events/jobs should be created
    jobs_after = models.Job.objects.filter(ready=True).count()
    events_after = models.Event.objects.count()
    self.assertEqual(events_after, events_before)
    self.assertEqual(jobs_after, jobs_before)

    repo = utils.create_repo(name='repo02', user=owner)
    branch = utils.create_branch(name='devel', repo=repo)
    utils.create_recipe(user=test_user, repo=repo, branch=branch, cause=models.Recipe.CAUSE_PUSH) # just create it so a job will get created

    response = self.client.post(reverse('ci:bitbucket:webhook', args=[test_user.build_key]), data=t1, content_type="application/json")
    self.assertEqual(response.content, "OK")

    jobs_after = models.Job.objects.filter(ready=True).count()
    events_after = models.Event.objects.count()
    self.assertGreater(events_after, events_before)
    self.assertGreater(jobs_after, jobs_before)
  """

  @patch.object(OAuth2Session, 'get')
  def test_get_repos(self, mock_get):
    user = utils.create_user_with_token(server=self.server)
    utils.simulate_login(self.client.session, user)
    auth = user.server.auth().start_session_for_user(user)
    gapi = api.BitBucketAPI()
    mock_get.return_value = utils.Response(json_data={'message': 'message'})
    repos = gapi.get_repos(auth, self.client.session)
    # shouldn't be any repos
    self.assertEqual(len(repos), 0)

    mock_get.return_value = utils.Response(json_data=[{'owner': user.name, 'name': 'repo1'}, {'owner': user.name, 'name': 'repo2'}])
    repos = gapi.get_repos(auth, self.client.session)
    self.assertEqual(len(repos), 2)

    session = self.client.session
    session['bitbucket_repos'] = ['newrepo1']
    session['bitbucket_org_repos'] = ['org/repo1']
    session.save()
    repos = gapi.get_repos(auth, self.client.session)
    self.assertEqual(len(repos), 1)
    self.assertEqual(repos[0], 'newrepo1')

  @patch.object(OAuth2Session, 'get')
  def test_get_org_repos(self, mock_get):
    user = utils.create_user_with_token(server=self.server)
    utils.simulate_login(self.client.session, user)
    auth = user.server.auth().start_session_for_user(user)
    gapi = api.BitBucketAPI()
    mock_get.return_value = utils.Response(json_data={'message': 'message'})
    repos = gapi.get_org_repos(auth, self.client.session)
    # shouldn't be any repos
    self.assertEqual(len(repos), 0)

    mock_get.return_value = utils.Response(json_data=[{'owner': 'org', 'name': 'repo1'}, {'owner': 'org', 'name': 'repo2'}])
    repos = gapi.get_org_repos(auth, self.client.session)
    self.assertEqual(len(repos), 2)

    session = self.client.session
    session['bitbucket_repos'] = ['newrepo1']
    session['bitbucket_org_repos'] = ['org/newrepo1']
    session.save()
    repos = gapi.get_org_repos(auth, self.client.session)
    self.assertEqual(len(repos), 1)
    self.assertEqual(repos[0], 'org/newrepo1')

  @patch.object(OAuth2Session, 'get')
  def test_get_branches(self, mock_get):
    user = utils.create_user_with_token(server=self.server)
    repo = utils.create_repo(user=user)
    utils.simulate_login(self.client.session, user)
    auth = user.server.auth().start_session_for_user(user)
    gapi = api.BitBucketAPI()
    mock_get.return_value = utils.Response(json_data={})
    branches = gapi.get_branches(auth, user, repo)
    # shouldn't be any branch
    self.assertEqual(len(branches), 0)

    mock_get.return_value = utils.Response(json_data={'branch1': 'info', 'branch2': 'info'})
    branches = gapi.get_branches(auth, user, repo)
    self.assertEqual(len(branches), 2)

  def test_update_pr_status(self):
    gapi = api.BitBucketAPI()
    gapi.update_pr_status('session', 'base', 'head', 'state', 'event_url', 'description', 'context')

  @patch.object(OAuth2Session, 'get')
  def test_is_collaborator(self, mock_get):
    user = utils.create_user_with_token(server=self.server)
    repo = utils.create_repo(user=user)
    gapi = api.BitBucketAPI()
    utils.simulate_login(self.client.session, user)
    auth = user.server.auth().start_session_for_user(user)
    # user is repo owner
    self.assertTrue(gapi.is_collaborator(auth, user, repo))
    user2 = utils.create_user('user2', server=self.server)
    repo = utils.create_repo(user=user2)
    # a collaborator
    mock_get.return_value = utils.Response(json_data={'values': [{'name': repo.name}]}, status_code=200)
    self.assertTrue(gapi.is_collaborator(auth, user, repo))
    # not a collaborator
    mock_get.return_value = utils.Response(status_code=404)
    self.assertFalse(gapi.is_collaborator(auth, user, repo))

  @patch.object(OAuth2Session, 'get')
  def test_last_sha(self, mock_get):
    user = utils.create_user_with_token(server=self.server)
    branch = utils.create_branch(user=user)
    gapi = api.BitBucketAPI()
    utils.simulate_login(self.client.session, user)
    auth = user.server.auth().start_session_for_user(user)
    mock_get.return_value = utils.Response(json_data={branch.name: {'raw_node': '123'}})
    sha = gapi.last_sha(auth, user.name, branch.repository.name, branch.name)
    self.assertEqual(sha, '123')

    mock_get.return_value = utils.Response()
    sha = gapi.last_sha(auth, user.name, branch.repository.name, branch.name)
    self.assertEqual(sha, None)

    mock_get.side_effect = Exception()
    sha = gapi.last_sha(auth, user.name, branch.repository.name, branch.name)
    self.assertEqual(sha, None)

  @patch.object(OAuth2Session, 'get')
  def test_get_all_pages(self, mock_get):
    user = utils.create_user_with_token(server=self.server)
    gapi = api.BitBucketAPI()
    utils.simulate_login(self.client.session, user)
    auth = user.server.auth().start_session_for_user(user)
    init_response = utils.Response(json_data=[{'foo': 'bar'}], use_links=True)
    mock_get.return_value = utils.Response(json_data=[{'bar': 'foo'}], use_links=False)
    all_json = gapi.get_all_pages(auth, init_response)
    self.assertEqual(len(all_json), 2)
    self.assertIn('foo', all_json[0])
    self.assertIn('bar', all_json[1])

  @patch.object(OAuth2Session, 'get')
  @patch.object(OAuth2Session, 'post')
  def test_install_webhooks(self, mock_post, mock_get):
    user = utils.create_user_with_token(server=self.server)
    repo = utils.create_repo(user=user)
    gapi = api.BitBucketAPI()
    utils.simulate_login(self.client.session, user)
    auth = user.server.auth().start_session_for_user(user)
    get_data ={'values': [{'events': ['pullrequest:created', 'repo:push'], 'url': 'no_url'}]}
    request = self.factory.get('/')
    callback_url = request.build_absolute_uri(reverse('ci:bitbucket:webhook', args=[user.build_key]))

    mock_get.return_value = utils.Response(json_data=get_data)
    mock_post.return_value = utils.Response(json_data={}, status_code=404)
    settings.INSTALL_WEBHOOK = True
    # with this data it should try to install the hook but there is an error
    with self.assertRaises(GitException):
      gapi.install_webhooks(request, auth, user, repo)

    # with this data it should do the hook
    mock_post.return_value = utils.Response(json_data={}, status_code=201)
    gapi.install_webhooks(request, auth, user, repo)

    # with this data the hook already exists
    get_data['values'][0]['url'] = callback_url
    gapi.install_webhooks(request, auth, user, repo)

    settings.INSTALL_WEBHOOK = False
    # this should just return
    gapi.install_webhooks(request, auth, user, repo)

  @patch.object(OAuth2Session, 'post')
  def test_pr_comment(self, mock_post):
    # no real state that we can check, so just go for coverage
    settings.REMOTE_UPDATE = True
    mock_post.return_value = utils.Response(status_code=200)
    bapi = api.BitBucketAPI()
    user = utils.create_user_with_token(server=self.server)
    utils.simulate_login(self.client.session, user)
    auth = user.server.auth().start_session_for_user(user)
    # valid post
    bapi.pr_comment(auth, 'url', 'message')

    # bad post
    mock_post.return_value = utils.Response(status_code=400, json_data={'message': 'bad post'})
    bapi.pr_comment(auth, 'url', 'message')

    # bad post
    mock_post.side_effect = Exception()
    bapi.pr_comment(auth, 'url', 'message')

    settings.REMOTE_UPDATE = False
    # should just return
    bapi.pr_comment(auth, 'url', 'message')

  def test_basic_coverage(self):
    gapi = api.BitBucketAPI()
    self.assertEqual(gapi.sign_in_url(), reverse('ci:bitbucket:sign_in'))
    gapi.user_url()
    gapi.repos_url()
    gapi.repo_url("owner", "repo")
    gapi.branches_url("owner", "repo")
    gapi.repo_html_url("owner", "repo")
    gapi.pr_html_url("owner", "repo", 1)
    gapi.branch_html_url("owner", "repo", "branch")
    gapi.git_url("owner", "repo")
    gapi.commit_html_url("owner", "repo", "1234")
    gapi.pr_comment_api_url("owner", "repo", 1)
    gapi.commit_comment_url("owner", "repo", "1234")
    gapi.collaborator_url("owner")
