from django.core.urlresolvers import reverse
from django.conf import settings
from requests_oauthlib import OAuth2Session
from ci.tests import utils as test_utils
from ci.github import api
from ci.git_api import GitException
from mock import patch
import os, json
from ci.tests import DBTester

class Tests(DBTester.DBTester):
  def setUp(self):
    super(Tests, self).setUp()
    self.create_default_recipes()

  def get_json_file(self, filename):
    dirname, fname = os.path.split(os.path.abspath(__file__))
    with open(dirname + '/' + filename, 'r') as f:
      js = f.read()
      return js

  def test_webhook_pr(self):
    """
    pr_open_01: testmb01 opens pull request from testmb01/repo01:devel to testmb/repo01:devel
    """
    url = reverse('ci:github:webhook', args=[self.build_user.build_key])
    # no recipes are there so no events/jobs should be created
    t1 = self.get_json_file('pr_open_01.json')
    self.set_counts()
    response = self.client.post(url, data=t1, content_type="application/json")
    self.assertEqual(response.content, "OK")
    self.compare_counts()

    # now there are recipes so jobs should get created
    py_data = json.loads(t1)
    py_data['pull_request']['base']['repo']['owner']['login'] = self.owner.name
    py_data['pull_request']['base']['repo']['name'] = self.repo.name

    self.set_counts()
    response = self.client.post(url, data=json.dumps(py_data), content_type="application/json")
    self.assertEqual(response.content, "OK")
    self.compare_counts(jobs=2, events=1, ready=1, users=1, repos=1, branches=1, commits=2, prs=1, active=2, active_repos=1)

  def test_webhook_push(self):
    """
    pr_push_01.json: testmb01 push from testmb01/repo02:devel to testmb/repo02:devel
    """
    t1 = self.get_json_file('push_01.json')
    url = reverse('ci:github:webhook', args=[self.build_user.build_key])
    # no recipes are there so no events/jobs should be created
    self.set_counts()
    response = self.client.post(url, data=t1, content_type="application/json")
    self.assertEqual(response.content, "OK")
    self.compare_counts()

    py_data = json.loads(t1)
    py_data['repository']['owner']['name'] = self.owner.name
    py_data['repository']['name'] = self.repo.name
    py_data['ref'] = 'refs/heads/{}'.format(self.branch.name)

    # now there are recipes so jobs should get created
    self.set_counts()
    response = self.client.post(url, data=json.dumps(py_data), content_type="application/json")
    self.assertEqual(response.content, "OK")
    self.compare_counts(jobs=2, ready=1, events=1, commits=2, active=2, active_repos=1)

  def test_status_str(self):
    gapi = api.GitHubAPI()
    self.assertEqual(gapi.status_str(gapi.SUCCESS), 'success')

  @patch.object(api.GitHubAPI, 'get_all_pages')
  @patch.object(OAuth2Session, 'get')
  def test_get_repos(self, mock_get, mock_get_all_pages):
    user = test_utils.create_user_with_token()
    test_utils.simulate_login(self.client.session, user)
    auth = user.server.auth().start_session_for_user(user)
    gapi = api.GitHubAPI()
    mock_get_all_pages.return_value = {'message': 'message'}
    mock_get.return_value = self.GetResponse(200)
    repos = gapi.get_repos(auth, self.client.session)
    # shouldn't be any repos
    self.assertEqual(len(repos), 0)

    mock_get_all_pages.return_value = [{'name': 'repo1', 'owner': {'login': 'owner'} }, {'name': 'repo2', 'owner': {'login': 'owner'}}]
    repos = gapi.get_repos(auth, self.client.session)
    self.assertEqual(len(repos), 2)

    session = self.client.session
    session['github_repos'] = ['owner/repo1']
    session.save()
    repos = gapi.get_repos(auth, self.client.session)
    self.assertEqual(len(repos), 1)
    self.assertEqual(repos[0], 'owner/repo1')

  @patch.object(api.GitHubAPI, 'get_all_pages')
  @patch.object(OAuth2Session, 'get')
  def test_get_org_repos(self, mock_get, mock_get_all_pages):
    user = test_utils.create_user_with_token()
    test_utils.simulate_login(self.client.session, user)
    auth = user.server.auth().start_session_for_user(user)
    gapi = api.GitHubAPI()
    mock_get_all_pages.return_value = {'message': 'message'}
    mock_get.return_value = self.GetResponse(200)
    repos = gapi.get_org_repos(auth, self.client.session)
    # shouldn't be any repos
    self.assertEqual(len(repos), 0)

    mock_get_all_pages.return_value = [{'name': 'repo1', 'owner':{'login':'owner'}}, {'name': 'repo2', 'owner':{'login':'owner'}}]
    repos = gapi.get_org_repos(auth, self.client.session)
    self.assertEqual(len(repos), 2)

    session = self.client.session
    session['github_org_repos'] = ['newrepo1']
    session.save()
    repos = gapi.get_org_repos(auth, self.client.session)
    self.assertEqual(len(repos), 1)
    self.assertEqual(repos[0], 'newrepo1')

  @patch.object(api.GitHubAPI, 'get_all_pages')
  @patch.object(OAuth2Session, 'get')
  def test_get_branches(self, mock_get, mock_get_all_pages):
    user = test_utils.create_user_with_token()
    repo = test_utils.create_repo(user=user)
    test_utils.simulate_login(self.client.session, user)
    auth = user.server.auth().start_session_for_user(user)
    gapi = api.GitHubAPI()
    mock_get_all_pages.return_value = {'message': 'message'}
    mock_get.return_value = self.GetResponse(200)
    branches = gapi.get_branches(auth, user, repo)
    # shouldn't be any branch
    self.assertEqual(len(branches), 0)

    mock_get_all_pages.return_value = [{'name': 'branch1'}, {'name': 'branch2'}]
    branches = gapi.get_branches(auth, user, repo)
    self.assertEqual(len(branches), 2)

  class PrResponse(object):
    def __init__(self, content):
      self.content = content

  @patch.object(OAuth2Session, 'post')
  def test_update_pr_status(self, mock_post):
    user = test_utils.create_user_with_token()
    gapi = api.GitHubAPI()
    test_utils.simulate_login(self.client.session, user)
    auth = user.server.auth().start_session_for_user(user)
    ev = test_utils.create_event(user=user)
    pr = test_utils.create_pr()
    ev.pull_request = pr
    ev.save()
    # no state is set so just run for coverage
    settings.REMOTE_UPDATE = True
    mock_post.return_value = self.PrResponse('updated_at')
    gapi.update_pr_status(auth, ev.base, ev.head, gapi.PENDING, 'event', 'desc', 'context')
    mock_post.return_value = self.PrResponse('nothing')
    gapi.update_pr_status(auth, ev.base, ev.head, gapi.PENDING, 'event', 'desc', 'context')
    mock_post.side_effect = Exception('exception')
    gapi.update_pr_status(auth, ev.base, ev.head, gapi.PENDING, 'event', 'desc', 'context')

    # This should just return
    settings.REMOTE_UPDATE = False
    gapi.update_pr_status(auth, ev.base, ev.head, gapi.PENDING, 'event', 'desc', 'context')

  class GetResponse(object):
    def __init__(self, status_code):
      self.status_code = status_code
    def json(self):
      return "json"

  @patch.object(OAuth2Session, 'get')
  def test_is_collaborator(self, mock_get):
    user = test_utils.create_user_with_token()
    repo = test_utils.create_repo(user=user)
    gapi = api.GitHubAPI()
    test_utils.simulate_login(self.client.session, user)
    auth = user.server.auth().start_session_for_user(user)
    # user is repo owner
    self.assertTrue(gapi.is_collaborator(auth, user, repo))
    user2 = test_utils.create_user('user2')
    repo = test_utils.create_repo(user=user2)
    # a collaborator
    mock_get.return_value = self.GetResponse(204)
    self.assertTrue(gapi.is_collaborator(auth, user, repo))
    # not a collaborator
    mock_get.return_value = self.GetResponse(404)
    self.assertFalse(gapi.is_collaborator(auth, user, repo))
    #doesn't have permission to check collaborator
    mock_get.return_value = self.GetResponse(403)
    self.assertFalse(gapi.is_collaborator(auth, user, repo))
    #some other response code
    mock_get.return_value = self.GetResponse(405)
    self.assertFalse(gapi.is_collaborator(auth, user, repo))

  class ShaResponse(test_utils.Response):
    def __init__(self, commit=True, *args, **kwargs):
      test_utils.Response.__init__(self, *args, **kwargs)
      if commit:
        self.content = '{\n\t"commit": {\n\t\t"sha": "123"\n\t}\n}'
      else:
        self.content = 'nothing'

  @patch.object(OAuth2Session, 'get')
  def test_last_sha(self, mock_get):
    user = test_utils.create_user_with_token()
    branch = test_utils.create_branch(user=user)
    gapi = api.GitHubAPI()
    test_utils.simulate_login(self.client.session, user)
    auth = user.server.auth().start_session_for_user(user)
    mock_get.return_value = self.ShaResponse(True)
    sha = gapi.last_sha(auth, user.name, branch.repository.name, branch.name)
    self.assertEqual(sha, '123')

    mock_get.return_value = self.ShaResponse(False)
    sha = gapi.last_sha(auth, user, branch.repository.name, branch.name)
    self.assertEqual(sha, None)

    mock_get.side_effect = Exception()
    sha = gapi.last_sha(auth, user, branch.repository.name, branch.name)
    self.assertEqual(sha, None)

  class LinkResponse(object):
    def __init__(self, json_dict, use_links=False, status_code=200, do_raise=False):
      if use_links:
        self.links = {'next': {'url': 'next_url'}}
      else:
        self.links = []
      self.json_dict = json_dict
      self.status_code = status_code
      self.do_raise = do_raise

    def json(self):
      return self.json_dict

    def raise_for_status(self):
      if self.do_raise:
        raise Exception("Bad Status!")

  @patch.object(OAuth2Session, 'get')
  def test_get_all_pages(self, mock_get):
    user = test_utils.create_user_with_token()
    gapi = api.GitHubAPI()
    test_utils.simulate_login(self.client.session, user)
    auth = user.server.auth().start_session_for_user(user)
    init_response = self.LinkResponse([{'foo': 'bar'}], True)
    mock_get.return_value = self.LinkResponse([{'bar': 'foo'}], False)
    all_json = gapi.get_all_pages(auth, init_response)
    self.assertEqual(len(all_json), 2)
    self.assertIn('foo', all_json[0])
    self.assertIn('bar', all_json[1])

  @patch.object(OAuth2Session, 'get')
  @patch.object(OAuth2Session, 'post')
  def test_install_webhooks(self, mock_post, mock_get):
    user = test_utils.create_user_with_token()
    repo = test_utils.create_repo(user=user)
    gapi = api.GitHubAPI()
    test_utils.simulate_login(self.client.session, user)
    auth = user.server.auth().start_session_for_user(user)
    get_data = []
    callback_url = "%s/%s" % (settings.WEBHOOK_BASE_URL, reverse('ci:github:webhook', args=[user.build_key]))
    get_data.append({'events': ['push'], 'config': {'url': 'no_url', 'content_type': 'json'}})
    mock_get.return_value = self.LinkResponse(get_data, False)
    mock_post.return_value = self.LinkResponse({'errors': 'error'}, False)
    settings.INSTALL_WEBHOOK = True
    # with this data it should try to install the hook but there is an error
    with self.assertRaises(GitException):
      gapi.install_webhooks(auth, user, repo)

    mock_post.return_value = self.LinkResponse({'errors': 'error'}, status_code=404, use_links=False)
    with self.assertRaises(GitException):
      gapi.install_webhooks(auth, user, repo)

    # with this data it should do the hook
    get_data.append({'events': ['pull_request', 'push'], 'config': {'url': 'no_url', 'content_type': 'json'}})
    mock_post.return_value = self.LinkResponse({}, False)
    gapi.install_webhooks(auth, user, repo)

    # with this data the hook already exists
    get_data.append({'events': ['pull_request', 'push'], 'config': {'url': callback_url, 'content_type': 'json'}})
    gapi.install_webhooks(auth, user, repo)

    settings.INSTALL_WEBHOOK = False
    # this should just return
    gapi.install_webhooks(auth, user, repo)

  @patch.object(OAuth2Session, 'get')
  @patch.object(OAuth2Session, 'delete')
  def test_remove_pr_todo_labels(self, mock_del, mock_get):
    # We can't really test this very well, so just try to get some coverage
    user = test_utils.create_user_with_token()
    repo = test_utils.create_repo(user=user)
    gapi = api.GitHubAPI()
    test_utils.simulate_login(self.client.session, user)

    # The title has the remove prefix so it would get deleted
    mock_get.return_value = self.LinkResponse([{"name": "%s Address Comments" % settings.GITHUB_REMOVE_PR_LABEL_PREFIX[0]}, {"name": "Other"}])
    mock_del.return_value = self.LinkResponse({})
    settings.REMOTE_UPDATE = True
    gapi.remove_pr_todo_labels(user, user.name, repo.name, 1)
    self.assertEqual(mock_get.call_count, 1)
    self.assertEqual(mock_del.call_count, 1)

    # The title has the remove prefix but the request raised an exception
    mock_del.return_value = self.LinkResponse({}, do_raise=True)
    mock_get.call_count = 0
    mock_del.call_count = 0
    gapi.remove_pr_todo_labels(user, user.name, repo.name, 1)
    self.assertEqual(mock_get.call_count, 1)
    self.assertEqual(mock_del.call_count, 1)

    # The title doesn't have the remove prefix
    mock_get.return_value = self.LinkResponse([{"name": "NOT A PREFIX Address Comments"}, {"name": "Other"}])
    mock_del.return_value = self.LinkResponse({})
    mock_get.call_count = 0
    mock_del.call_count = 0
    gapi.remove_pr_todo_labels(user, user.name, repo.name, 1)
    self.assertEqual(mock_get.call_count, 1)
    self.assertEqual(mock_del.call_count, 0)

    # We aren't updating the server
    settings.REMOTE_UPDATE = False
    mock_get.call_count = 0
    mock_del.call_count = 0
    gapi.remove_pr_todo_labels(user, user.name, repo.name, 1)
    self.assertEqual(mock_get.call_count, 0)
    self.assertEqual(mock_del.call_count, 0)
