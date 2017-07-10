
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
        self.gapi = api.GitLabAPI()
        utils.simulate_login(self.client.session, self.build_user)
        self.auth = self.build_user.server.auth().start_session_for_user(self.build_user)

    def tearDown(self):
        super(Tests, self).tearDown()
        settings.GITLAB_HOSTNAME = self.old_hostname
        settings.INSTALLED_GITSERVERS = self.old_installed

    def get_json_file(self, filename):
        dirname, fname = os.path.split(os.path.abspath(__file__))
        with open(dirname + '/' + filename, 'r') as f:
            js = f.read()
            return js

    @patch.object(requests, 'get')
    def test_get_repos(self, mock_get):
        mock_get.return_value = utils.Response([])
        repos = self.gapi.get_repos(self.auth, self.client.session)
        # shouldn't be any repos
        self.assertEqual(len(repos), 0)

        data = [{'namespace': {'name': self.build_user.name}, 'name': 'repo2'},
                {'namespace': {'name': self.build_user.name}, 'name': 'repo2'}]
        mock_get.return_value = utils.Response(data)
        repos = self.gapi.get_repos(self.auth, self.client.session)
        self.assertEqual(len(repos), 2)

        session = self.client.session
        session['gitlab_repos'] = ['repo1']
        session.save()
        repos = self.gapi.get_repos(self.auth, self.client.session)
        self.assertEqual(len(repos), 1)
        self.assertEqual(repos[0], 'repo1')

    @patch.object(requests, 'get')
    def test_get_org_repos(self, mock_get):
        mock_get.return_value = utils.Response([])
        repos = self.gapi.get_org_repos(self.auth, self.client.session)
        # shouldn't be any repos
        self.assertEqual(len(repos), 0)

        data = [{'namespace': {'name': 'name'}, 'name': 'repo2'},
                {'namespace': {'name': 'name'}, 'name': 'repo2'}]
        mock_get.return_value = utils.Response(data)
        repos = self.gapi.get_org_repos(self.auth, self.client.session)
        self.assertEqual(len(repos), 2)

        session = self.client.session
        session['gitlab_org_repos'] = ['newrepo1']
        session.save()
        repos = self.gapi.get_org_repos(self.auth, self.client.session)
        self.assertEqual(len(repos), 1)
        self.assertEqual(repos[0], 'newrepo1')

    @patch.object(requests, 'get')
    def test_get_all_repos(self, mock_get):
        mock_get.return_value = utils.Response([])
        repos = self.gapi.get_all_repos(self.auth, self.build_user.name)
        # shouldn't be any repos
        self.assertEqual(len(repos), 0)

        data = [{'namespace': {'name': 'name'}, 'name': 'repo1'},
                {'namespace': {'name': 'name'}, 'name': 'repo2'},
                {'namespace': {'name': 'other'}, 'name': 'repo1'},
                {'namespace': {'name': 'other'}, 'name': 'repo2'},
                ]
        mock_get.return_value = utils.Response(data)
        repos = self.gapi.get_all_repos(self.auth, "name")
        self.assertEqual(len(repos), 4)

    @patch.object(requests, 'get')
    def test_get_branches(self, mock_get):
        mock_get.return_value = utils.Response([])
        branches = self.gapi.get_branches(self.auth, self.owner, self.repo)
        # shouldn't be any branch
        self.assertEqual(len(branches), 0)

        data = [{'name': 'branch1'},
                {'name': 'branch2'}]
        mock_get.return_value = utils.Response(data)
        branches = self.gapi.get_branches(self.auth, self.owner, self.repo)
        self.assertEqual(len(branches), 2)

    @patch.object(requests, 'get')
    def test_get_group_id(self, mock_get):
        token = self.build_user.token
        mock_get.return_value = utils.Response([{'name': self.build_user.name, 'id': 42}])
        group_id = self.gapi.get_group_id(self.auth, token, self.build_user.name)
        self.assertEqual(group_id, 42)

    @patch.object(requests, 'get')
    def test_is_group_member(self, mock_get):
        token = self.build_user.token
        mock_get.return_value = utils.Response([{'username': self.build_user.name}])
        ret = self.gapi.is_group_member(self.auth, token, 42, self.build_user.name)
        self.assertTrue(ret)
        mock_get.return_value = utils.Response([])
        ret = self.gapi.is_group_member(self.auth, token, 42, self.build_user.name)
        self.assertFalse(ret)

    @patch.object(requests, 'get')
    def test_is_collaborator(self, mock_get):
        # user is repo owner
        self.assertTrue(self.gapi.is_collaborator(self.auth, self.owner, self.repo))
        user2 = utils.create_user('user2', server=self.server)

        # a collaborator
        repo = utils.create_repo(user=user2)
        mock_get.return_value = utils.Response([{'username': self.build_user.name}])
        self.assertTrue(self.gapi.is_collaborator(self.auth, self.build_user, repo))

        # not a collaborator
        mock_get.return_value = utils.Response([{'username': 'none'}])
        self.assertFalse(self.gapi.is_collaborator(self.auth, self.build_user, repo))

    class ShaResponse(object):
        def __init__(self, commit=True):
            if commit:
                self.content = '{\n\t"commit": {\n\t\t"id": "123"\n\t}\n}'
            else:
                self.content = 'nothing'

    @patch.object(requests, 'get')
    def test_last_sha(self, mock_get):
        mock_get.return_value = self.ShaResponse(True)
        sha = self.gapi.last_sha(self.auth, self.build_user, self.branch.repository, self.branch)
        self.assertEqual(sha, '123')

        mock_get.return_value = self.ShaResponse(False)
        sha = self.gapi.last_sha(self.auth, self.build_user, self.branch.repository, self.branch)
        self.assertEqual(sha, None)

        mock_get.side_effect = Exception()
        sha = self.gapi.last_sha(self.auth, self.build_user, self.branch.repository, self.branch)
        self.assertEqual(sha, None)


    @patch.object(requests, 'get')
    def test_get_all_pages(self, mock_get):
        init_response = utils.Response([{'foo': 'bar'}], use_links=True)
        mock_get.return_value = utils.Response([{'bar': 'foo'}])
        all_json = self.gapi.get_all_pages(self.auth, init_response)
        self.assertEqual(len(all_json), 2)
        self.assertIn('foo', all_json[0])
        self.assertIn('bar', all_json[1])

    @patch.object(requests, 'get')
    @patch.object(requests, 'post')
    def test_install_webhooks(self, mock_post, mock_get):
        get_data = []
        webhook_url = reverse('ci:gitlab:webhook', args=[self.build_user.build_key])
        callback_url = "%s%s" % (settings.WEBHOOK_BASE_URL, webhook_url)
        get_data.append({'merge_requests_events': 'true', 'push_events': 'true', 'url': 'no_url'})
        mock_get.return_value = utils.Response(get_data, False)
        mock_post.return_value = utils.Response({'errors': 'error'}, status_code=404)
        settings.INSTALL_WEBHOOK = True
        # with this data it should try to install the hook but there is an error
        with self.assertRaises(GitException):
            self.gapi.install_webhooks(self.auth, self.build_user, self.repo)

        # with this data it should do the hook
        mock_post.return_value = utils.Response([], False)
        self.gapi.install_webhooks(self.auth, self.build_user, self.repo)

        # with this data the hook already exists
        get_data.append({'merge_requests_events': 'true', 'push_events': 'true', 'url': callback_url })
        self.gapi.install_webhooks(self.auth, self.build_user, self.repo)

        settings.INSTALL_WEBHOOK = False
        # this should just return
        self.gapi.install_webhooks(self.auth, self.build_user, self.repo)

    @patch.object(requests, 'post')
    def test_post(self, mock_post):
        mock_post.return_value = '123'
        # should just return whatever requests.post returns
        self.assertEqual(self.gapi.post('url', 'token', {}), '123')

    @patch.object(requests, 'get')
    def test_get(self, mock_get):
        mock_get.return_value = '123'
        # should just return whatever requests.get returns
        self.assertEqual(self.gapi.get('url', 'token'), '123')

    @patch.object(requests, 'post')
    def test_pr_comment(self, mock_post):
        # no real state that we can check, so just go for coverage
        settings.REMOTE_UPDATE = True
        mock_post.return_value = utils.Response(json_data="some json")
        # valid post
        self.gapi.pr_comment(self.auth, 'url', 'message')
        self.gapi.pr_job_status_comment(self.auth, 'url', 'message')

        # bad post
        mock_post.side_effect = Exception()
        self.gapi.pr_comment(self.auth, 'url', 'message')

        settings.REMOTE_UPDATE = False
        # should just return
        self.gapi.pr_comment(self.auth, 'url', 'message')

    @patch.object(requests, 'post')
    def test_update_pr_status(self, mock_post):
        ev = utils.create_event(user=self.build_user)
        pr = utils.create_pr()
        ev.pull_request = pr
        ev.save()
        # no state is set so just run for coverage
        settings.REMOTE_UPDATE = True
        mock_post.return_value = utils.Response(status_code=200, content="some content")
        self.gapi.update_pr_status(self.auth, ev.base, ev.head, self.gapi.PENDING, 'event', 'desc', 'context', self.gapi.STATUS_JOB_STARTED)
        self.assertEqual(mock_post.call_count, 1)

        self.gapi.update_pr_status(self.auth, ev.base, ev.head, self.gapi.PENDING, 'event', 'desc', 'context', self.gapi.STATUS_CONTINUE_RUNNING)
        self.assertEqual(mock_post.call_count, 1)

        self.gapi.update_pr_status(self.auth, ev.base, ev.head, self.gapi.PENDING, 'event', 'desc', 'context', self.gapi.STATUS_START_RUNNING)
        self.assertEqual(mock_post.call_count, 2)

        mock_post.return_value = utils.Response(status_code=404, content="nothing")
        self.gapi.update_pr_status(self.auth, ev.base, ev.head, self.gapi.PENDING, 'event', 'desc', 'context', self.gapi.STATUS_JOB_STARTED)
        self.assertEqual(mock_post.call_count, 3)

        mock_post.side_effect = Exception('exception')
        self.gapi.update_pr_status(self.auth, ev.base, ev.head, self.gapi.PENDING, 'event', 'desc', 'context', self.gapi.STATUS_JOB_STARTED)
        self.assertEqual(mock_post.call_count, 4)

        # This should just return
        settings.REMOTE_UPDATE = False
        self.gapi.update_pr_status(self.auth, ev.base, ev.head, self.gapi.PENDING, 'event', 'desc', 'context', self.gapi.STATUS_JOB_STARTED)
        self.assertEqual(mock_post.call_count, 4)

    def test_branch_urls(self):
        url = self.gapi.branch_url(self.branch.user().name, self.branch.repository.name, self.branch.name)
        bstr = "branches/%s" % self.branch.name
        self.assertIn(bstr, url)
        url = self.gapi.branch_by_id_url(42, self.branch.name)
        self.assertIn(bstr, url)

        self.branch.name = "test#branch"
        self.branch.save()
        url = self.gapi.branch_url(self.branch.user().name, self.branch.repository.name, self.branch.name)
        self.assertIn("branches/test%23branch", url)
        url = self.gapi.branch_by_id_url(42, self.branch.name)
        self.assertIn("branches/test%23branch", url)

    def test_basic_coverage(self):
        self.gapi.git_url("owner", "repo")
        self.gapi.sign_in_url()
        self.gapi.users_url()
        self.gapi.user_url(1)
        self.gapi.repos_url()
        self.gapi.orgs_url()
        self.gapi.projects_url()
        self.gapi.gitlab_id("owner", "repo")
        self.gapi.repo_url("owner", "repo")
        self.gapi.branches_url("owner", "repo")
        self.gapi.branch_by_id_url(1, 2)
        self.gapi.branch_url("owner", "repo", "branch")
        self.gapi.branch_html_url("owner", "repo", "branch")
        self.gapi.repo_html_url("owner", "repo")
        self.gapi.comment_api_url(1, 2)
        self.gapi.commit_html_url("owner", "repo", "sha")
        self.gapi.pr_html_url("owner", "repo", 1)
        self.gapi.internal_pr_html_url("repo_path", 1)
        self.gapi.members_url("owner", "repo")
        self.gapi.groups_url()
        self.gapi.group_members_url(1)

    def test_status_str(self):
        self.assertEqual(self.gapi.status_str(self.gapi.SUCCESS), 'success')
        self.assertEqual(self.gapi.status_str(1000), None)

    @patch.object(requests, 'get')
    def test_get_pr_changed_files(self, mock_get):
        pr = utils.create_pr(repo=self.repo)
        mock_get.return_value = utils.Response({"changes": []})
        files = self.gapi.get_pr_changed_files(self.auth, self.repo.user.name, self.repo.name, pr.number)
        # shouldn't be any files
        self.assertEqual(len(files), 0)

        file_json = self.get_json_file("files.json")
        file_data = json.loads(file_json)
        mock_get.return_value = utils.Response(file_data)
        files = self.gapi.get_pr_changed_files(self.auth, self.repo.user.name, self.repo.name, pr.number)
        self.assertEqual(len(files), 2)
        self.assertEqual(["other/path/to/file1", "path/to/file0"], files)

        # simulate a bad request
        mock_get.return_value = utils.Response(file_data, status_code=400)
        files = self.gapi.get_pr_changed_files(self.auth, self.repo.user.name, self.repo.name, pr.number)
        self.assertEqual(files, [])

        # simulate a request timeout
        mock_get.side_effect = Exception("Bam!")
        files = self.gapi.get_pr_changed_files(self.auth, self.repo.user.name, self.repo.name, pr.number)
        self.assertEqual(files, [])

    @patch.object(requests, 'get')
    def test_get_project_access_level(self, mock_get):
        mock_get.return_value = utils.Response({}, status_code=200)
        level = self.gapi.get_project_access_level(self.auth, self.repo.user.name, self.repo.name)
        self.assertEqual(level, "Unknown")

        user_json = self.get_json_file("user.json")
        user_data = json.loads(user_json)

        mock_get.return_value = None
        mock_get.side_effect = [utils.Response(user_data), utils.Response({}, status_code=400)]
        level = self.gapi.get_project_access_level(self.auth, self.repo.user.name, self.repo.name)
        self.assertEqual(level, "Unknown")

        members_json = self.get_json_file("project_member.json")
        members_data = json.loads(members_json)
        mock_get.side_effect = [utils.Response(user_data), utils.Response(members_data)]
        level = self.gapi.get_project_access_level(self.auth, self.repo.user.name, self.repo.name)
        self.assertEqual(level, "Reporter")

        members_data["access_level"] = 30
        mock_get.side_effect = [utils.Response(user_data), utils.Response(members_data)]
        level = self.gapi.get_project_access_level(self.auth, self.repo.user.name, self.repo.name)
        self.assertEqual(level, "Developer")

        mock_get.side_effect = Exception("Bam!")
        level = self.gapi.get_project_access_level(self.auth, self.repo.user.name, self.repo.name)
        self.assertEqual(level, "Unknown")

    @patch.object(requests, 'get')
    def test_get_pr_comments(self, mock_get):
        settings.REMOTE_UPDATE = False
        # should just return
        ret = self.gapi.get_pr_comments(None, None, None, None)
        self.assertEqual(mock_get.call_count, 0)
        self.assertEqual(ret, [])

        settings.REMOTE_UPDATE = True
        # bad response, should return empty list
        mock_get.return_value = utils.Response(status_code=400)
        comment_re = r"^some message"
        ret = self.gapi.get_pr_comments(self.auth, "some_url", self.build_user.name, comment_re)
        self.assertEqual(mock_get.call_count, 1)
        self.assertEqual(ret, [])

        c0 = {"author": {"username": self.build_user.name}, "body": "some message", "id": 1}
        c1 = {"author": {"username": self.build_user.name}, "body": "other message", "id": 1}
        c2 = {"author": {"username": "nobody"}, "body": "some message", "id": 1}
        mock_get.return_value = utils.Response(json_data=[c0, c1, c2])

        ret = self.gapi.get_pr_comments(self.auth, "some_url", self.build_user.name, comment_re)
        self.assertEqual(ret, [c0])

    @patch.object(requests, 'delete')
    def test_remove_pr_comment(self, mock_del):
        settings.REMOTE_UPDATE = False
        # should just return
        self.gapi.remove_pr_comment(None, None)
        self.assertEqual(mock_del.call_count, 0)

        settings.REMOTE_UPDATE = True

        comment = {"url": "some_url"}

        # bad response
        mock_del.return_value = utils.Response(status_code=400)
        self.gapi.remove_pr_comment(self.auth, comment)
        self.assertEqual(mock_del.call_count, 1)

        # good response
        mock_del.return_value = utils.Response()
        self.gapi.remove_pr_comment(self.auth, comment)
        self.assertEqual(mock_del.call_count, 2)

    @patch.object(requests, 'put')
    def test_edit_pr_comment(self, mock_edit):
        settings.REMOTE_UPDATE = False
        # should just return
        self.gapi.edit_pr_comment(None, None, None)
        self.assertEqual(mock_edit.call_count, 0)

        settings.REMOTE_UPDATE = True

        comment = {"url": "some_url"}
        # bad response
        mock_edit.return_value = utils.Response(status_code=400)
        self.gapi.edit_pr_comment(self.auth, comment, "new msg")
        self.assertEqual(mock_edit.call_count, 1)

        # good response
        mock_edit.return_value = utils.Response()
        self.gapi.edit_pr_comment(self.auth, comment, "new msg")
        self.assertEqual(mock_edit.call_count, 2)

    def test_unimplemented(self):
        """
        Just get coverage on the warning messages for the unimplementd functions
        """
        gapi = api.GitLabAPI()
        gapi.add_pr_label(None, None, None, None)
        gapi.remove_pr_label(None, None, None, None)
