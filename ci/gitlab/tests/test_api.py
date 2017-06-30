
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

from django.core.urlresolvers import reverse
from django.conf import settings
from ci.tests import utils
from ci.gitlab import api
from ci.git_api import GitException
from mock import patch
import requests
import os, json
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

    def get_json_file(self, filename):
        dirname, fname = os.path.split(os.path.abspath(__file__))
        with open(dirname + '/' + filename, 'r') as f:
            js = f.read()
            return js

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

        def raise_for_status(self):
            if self.status_code >= 400:
                raise Exception("Bad status code")

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
    def test_get_all_repos(self, mock_get):
        user = utils.create_user_with_token(server=self.server)
        utils.simulate_login(self.client.session, user)
        auth = user.server.auth().start_session_for_user(user)
        gapi = api.GitLabAPI()
        mock_get.return_value = self.LinkResponse([])
        repos = gapi.get_all_repos(auth, user.name)
        # shouldn't be any repos
        self.assertEqual(len(repos), 0)

        mock_get.return_value = self.LinkResponse([
          {'namespace': {'name': 'name'}, 'name': 'repo1'},
          {'namespace': {'name': 'name'}, 'name': 'repo2'},
          {'namespace': {'name': 'other'}, 'name': 'repo1'},
          {'namespace': {'name': 'other'}, 'name': 'repo2'},
          ])
        repos = gapi.get_all_repos(auth, "name")
        self.assertEqual(len(repos), 4)

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
        callback_url = "%s%s" % (settings.WEBHOOK_BASE_URL, reverse('ci:gitlab:webhook', args=[user.build_key]))
        get_data.append({'merge_requests_events': 'true', 'push_events': 'true', 'url': 'no_url'})
        mock_get.return_value = self.LinkResponse(get_data, False)
        mock_post.return_value = self.LinkResponse({'errors': 'error'}, False, 404)
        settings.INSTALL_WEBHOOK = True
        # with this data it should try to install the hook but there is an error
        with self.assertRaises(GitException):
            gapi.install_webhooks(auth, user, repo)

        # with this data it should do the hook
        mock_post.return_value = self.LinkResponse([], False)
        gapi.install_webhooks(auth, user, repo)

        # with this data the hook already exists
        get_data.append({'merge_requests_events': 'true', 'push_events': 'true', 'url': callback_url })
        gapi.install_webhooks(auth, user, repo)

        settings.INSTALL_WEBHOOK = False
        # this should just return
        gapi.install_webhooks(auth, user, repo)

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

    @patch.object(requests, 'post')
    def test_pr_comment(self, mock_post):
        # no real state that we can check, so just go for coverage
        settings.REMOTE_UPDATE = True
        mock_post.return_value = utils.Response(json_data="some json")
        gapi = api.GitLabAPI()
        user = utils.create_user_with_token(server=self.server)
        utils.simulate_login(self.client.session, user)
        auth = user.server.auth().start_session_for_user(user)
        # valid post
        gapi.pr_comment(auth, 'url', 'message')
        gapi.pr_job_status_comment(auth, 'url', 'message')

        # bad post
        mock_post.side_effect = Exception()
        gapi.pr_comment(auth, 'url', 'message')

        settings.REMOTE_UPDATE = False
        # should just return
        gapi.pr_comment(auth, 'url', 'message')

    @patch.object(requests, 'post')
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
        mock_post.return_value = utils.Response(status_code=200, content="some content")
        gapi.update_pr_status(auth, ev.base, ev.head, gapi.PENDING, 'event', 'desc', 'context', gapi.STATUS_JOB_STARTED)
        self.assertEqual(mock_post.call_count, 1)

        gapi.update_pr_status(auth, ev.base, ev.head, gapi.PENDING, 'event', 'desc', 'context', gapi.STATUS_CONTINUE_RUNNING)
        self.assertEqual(mock_post.call_count, 1)

        gapi.update_pr_status(auth, ev.base, ev.head, gapi.PENDING, 'event', 'desc', 'context', gapi.STATUS_START_RUNNING)
        self.assertEqual(mock_post.call_count, 2)

        mock_post.return_value = utils.Response(status_code=404, content="nothing")
        gapi.update_pr_status(auth, ev.base, ev.head, gapi.PENDING, 'event', 'desc', 'context', gapi.STATUS_JOB_STARTED)
        self.assertEqual(mock_post.call_count, 3)

        mock_post.side_effect = Exception('exception')
        gapi.update_pr_status(auth, ev.base, ev.head, gapi.PENDING, 'event', 'desc', 'context', gapi.STATUS_JOB_STARTED)
        self.assertEqual(mock_post.call_count, 4)

        # This should just return
        settings.REMOTE_UPDATE = False
        gapi.update_pr_status(auth, ev.base, ev.head, gapi.PENDING, 'event', 'desc', 'context', gapi.STATUS_JOB_STARTED)
        self.assertEqual(mock_post.call_count, 4)

    def test_branch_urls(self):
        branch = utils.create_branch(name="test_branch")
        gapi = api.GitLabAPI()
        url = gapi.branch_url(branch.user().name, branch.repository.name, branch.name)
        self.assertIn("branches/test_branch", url)
        url = gapi.branch_by_id_url(42, branch.name)
        self.assertIn("branches/test_branch", url)

        branch.name = "test#branch"
        branch.save()
        url = gapi.branch_url(branch.user().name, branch.repository.name, branch.name)
        self.assertIn("branches/test%23branch", url)
        url = gapi.branch_by_id_url(42, branch.name)
        self.assertIn("branches/test%23branch", url)

    def test_basic_coverage(self):
        gapi = api.GitLabAPI()
        gapi.git_url("owner", "repo")
        gapi.sign_in_url()
        gapi.users_url()
        gapi.user_url(1)
        gapi.repos_url()
        gapi.orgs_url()
        gapi.projects_url()
        gapi.gitlab_id("owner", "repo")
        gapi.repo_url("owner", "repo")
        gapi.branches_url("owner", "repo")
        gapi.branch_by_id_url(1, 2)
        gapi.branch_url("owner", "repo", "branch")
        gapi.branch_html_url("owner", "repo", "branch")
        gapi.repo_html_url("owner", "repo")
        gapi.comment_api_url(1, 2)
        gapi.commit_html_url("owner", "repo", "sha")
        gapi.pr_html_url("owner", "repo", 1)
        gapi.internal_pr_html_url("repo_path", 1)
        gapi.members_url("owner", "repo")
        gapi.groups_url()
        gapi.group_members_url(1)

    def test_status_str(self):
        gapi = api.GitLabAPI()
        self.assertEqual(gapi.status_str(gapi.SUCCESS), 'success')
        self.assertEqual(gapi.status_str(1000), None)

    @patch.object(api.GitLabAPI, 'get')
    def test_get_pr_changed_files(self, mock_get):
        user = utils.create_user_with_token(server=self.server)
        utils.simulate_login(self.client.session, user)
        auth = user.server.auth().start_session_for_user(user)
        gapi = api.GitLabAPI()
        pr = utils.create_pr(repo=self.repo)
        mock_get.return_value = self.LinkResponse({"changes": []})
        files = gapi.get_pr_changed_files(auth, self.repo.user.name, self.repo.name, pr.number)
        # shouldn't be any files
        self.assertEqual(len(files), 0)

        file_json = self.get_json_file("files.json")
        file_data = json.loads(file_json)
        mock_get.return_value = self.LinkResponse(file_data)
        files = gapi.get_pr_changed_files(auth, self.repo.user.name, self.repo.name, pr.number)
        self.assertEqual(len(files), 2)
        self.assertEqual(["other/path/to/file1", "path/to/file0"], files)

        # simulate a bad request
        mock_get.return_value = self.LinkResponse(file_data, status_code=400)
        files = gapi.get_pr_changed_files(auth, self.repo.user.name, self.repo.name, pr.number)
        self.assertEqual(files, [])

        # simulate a request timeout
        mock_get.side_effect = Exception("Bam!")
        files = gapi.get_pr_changed_files(auth, self.repo.user.name, self.repo.name, pr.number)
        self.assertEqual(files, [])

    @patch.object(api.GitLabAPI, 'get')
    def test_get_project_access_level(self, mock_get):
        user = utils.create_user_with_token(server=self.server)
        utils.simulate_login(self.client.session, user)
        auth = user.server.auth().start_session_for_user(user)
        gapi = api.GitLabAPI()
        mock_get.return_value = self.LinkResponse({}, status_code=200)
        level = gapi.get_project_access_level(auth, self.repo.user.name, self.repo.name)
        self.assertEqual(level, "Unknown")

        user_json = self.get_json_file("user.json")
        user_data = json.loads(user_json)

        mock_get.return_value = None
        mock_get.side_effect = [self.LinkResponse(user_data), self.LinkResponse({}, status_code=400)]
        level = gapi.get_project_access_level(auth, self.repo.user.name, self.repo.name)
        self.assertEqual(level, "Unknown")

        members_json = self.get_json_file("project_member.json")
        members_data = json.loads(members_json)
        mock_get.side_effect = [self.LinkResponse(user_data), self.LinkResponse(members_data)]
        level = gapi.get_project_access_level(auth, self.repo.user.name, self.repo.name)
        self.assertEqual(level, "Reporter")

        members_data["access_level"] = 30
        mock_get.side_effect = [self.LinkResponse(user_data), self.LinkResponse(members_data)]
        level = gapi.get_project_access_level(auth, self.repo.user.name, self.repo.name)
        self.assertEqual(level, "Developer")

        mock_get.side_effect = Exception("Bam!")
        level = gapi.get_project_access_level(auth, self.repo.user.name, self.repo.name)
        self.assertEqual(level, "Unknown")

    def test_unimplemented(self):
        """
        Just get coverage on the warning messages for the unimplementd functions
        """
        gapi = api.GitLabAPI()
        gapi.add_pr_label(None, None, None, None)
        gapi.remove_pr_label(None, None, None, None)
        gapi.get_pr_comments(None, None, None, None)
        gapi.remove_pr_comment(None, None, None)
        gapi.edit_pr_comment(None, None, None, None)
