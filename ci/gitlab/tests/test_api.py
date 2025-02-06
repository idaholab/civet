
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

from __future__ import unicode_literals, absolute_import
from django.urls import reverse
from django.conf import settings
from django.test import override_settings
from ci.tests import utils
from ci.git_api import GitException
from mock import patch
import requests
import os, json
from ci.tests import DBTester
from requests_oauthlib import OAuth2Session

@override_settings(INSTALLED_GITSERVERS=[utils.gitlab_config()])
class Tests(DBTester.DBTester):
    def setUp(self):
        super(Tests, self).setUp()
        self.create_default_recipes(server_type=settings.GITSERVER_GITLAB)
        utils.simulate_login(self.client.session, self.build_user)

    def get_json_file(self, filename):
        dirname, fname = os.path.split(os.path.abspath(__file__))
        with open(dirname + '/' + filename, 'r') as f:
            js = f.read()
            return js

    def test_misc(self):
        # Just get some basic coverage
        api = self.server.api(token="1234")
        self.build_user.token = json.dumps({'access_token': 1234})
        self.build_user.save()
        api = self.build_user.api()
        api.sign_in_url()
        api.branch_html_url("owner", "repo", "branch")
        api.repo_html_url("owner", "repo")
        api.commit_html_url("owner", "repo", "sha")

    def test_can_view_repo(self):
        api = self.server.api()
        api._api_url = 'https://gitlab.com/api/v4'

        petsc_exists = api.can_view_repo('petsc', 'petsc')
        self.assertTrue(petsc_exists)

        bad_repo_exists = api.can_view_repo('foobar123', 'bazbang456')
        self.assertFalse(bad_repo_exists)

    @patch.object(requests, 'get')
    def test_get_repos(self, mock_get):
        api = self.server.api()
        mock_get.return_value = utils.Response([])
        repos = api.get_repos(self.client.session)
        # shouldn't be any repos
        self.assertEqual(len(repos), 0)

        data = [{'path_with_namespace': "%s/repo2" % self.build_user.name},
                {'path_with_namespace': "%s/repo2" % self.build_user.name},
                ]
        mock_get.return_value = utils.Response(data)
        repos = api.get_repos(self.client.session)
        self.assertEqual(len(repos), 2)

        session = self.client.session
        session[api._repos_key] = ['repo1']
        session.save()
        repos = api.get_repos(self.client.session)
        self.assertEqual(len(repos), 1)
        self.assertEqual(repos[0], 'repo1')

    @patch.object(requests, 'get')
    def test_get_user_org_repos(self, mock_get):
        mock_get.return_value = utils.Response(status_code=404)
        api = self.server.api()
        repos = api._get_user_org_repos(self.build_user)
        self.assertEqual(repos, [])

        data = [{'path_with_namespace': "name/repo2"},
                {'path_with_namespace': "name/repo1"},
                ]
        mock_get.return_value = utils.Response(data)
        repos = api._get_user_org_repos(self.build_user)
        self.assertEqual(repos, ["name/repo1", "name/repo2"])

    @patch.object(requests, 'get')
    def test_get_all_repos(self, mock_get):
        mock_get.return_value = utils.Response([])
        api = self.server.api()
        repos = api.get_all_repos(self.build_user.name)
        # shouldn't be any repos
        self.assertEqual(len(repos), 0)

        data = [{'path_with_namespace': "name/repo1"},
                {'path_with_namespace': "name/repo2"},
                {'path_with_namespace': "other/repo1"},
                {'path_with_namespace': "other/repo2"},
                ]
        mock_get.return_value = utils.Response(data)
        repos = api.get_all_repos("name")
        self.assertEqual(len(repos), 4)

    @patch.object(requests, 'get')
    def test_get_branches(self, mock_get):
        mock_get.return_value = utils.Response([])
        api = self.server.api()
        path_with_namespace = '%s/%s' % (self.owner.name, self.repo.name)
        branches = api.get_branches(path_with_namespace)
        # shouldn't be any branch
        self.assertEqual(len(branches), 0)

        data = [{'name': 'branch1'},
                {'name': 'branch2'}]
        mock_get.return_value = utils.Response(data)
        branches = api.get_branches(path_with_namespace)
        self.assertEqual(len(branches), 2)

    @patch.object(requests, 'get')
    def test_is_group_member(self, mock_get):
        mock_get.return_value = utils.Response([{'username': self.build_user.name}])
        api = self.server.api()
        ret = api._is_group_member(42, self.build_user.name)
        self.assertIs(ret, True)
        mock_get.return_value = utils.Response([])
        ret = api._is_group_member(42, self.build_user.name)
        self.assertIs(ret, False)

    @patch.object(requests, 'get')
    def test_is_collaborator(self, mock_get):
        # user is repo owner
        api = self.server.api()
        self.assertTrue(api.is_collaborator(self.owner, self.repo))
        user2 = utils.create_user('user2', server=self.server)

        # a collaborator
        repo = utils.create_repo(user=user2)
        mock_get.return_value = utils.Response([{'username': self.build_user.name}])
        self.assertTrue(api.is_collaborator(self.build_user, repo))

        # not a collaborator
        mock_get.return_value = utils.Response([{'username': 'none'}])
        self.assertFalse(api.is_collaborator(self.build_user, repo))

        # some random problem
        mock_get.side_effect = Exception("Bam!")
        self.assertFalse(api.is_collaborator(self.build_user, repo))

    @patch.object(requests, 'get')
    def test_last_sha(self, mock_get):
        data = {"commit": {"id": "123"}}
        mock_get.return_value = utils.Response(data)
        api = self.server.api()
        sha = api.last_sha(self.build_user, self.branch.repository, self.branch)
        self.assertEqual(sha, '123')

        mock_get.return_value = utils.Response(status_code=404)
        sha = api.last_sha(self.build_user, self.branch.repository, self.branch)
        self.assertEqual(sha, None)

        mock_get.side_effect = Exception("Bam!")
        sha = api.last_sha(self.build_user, self.branch.repository, self.branch)
        self.assertEqual(sha, None)

    @patch.object(requests, 'get')
    @patch.object(requests, 'post')
    @override_settings(INSTALLED_GITSERVERS=[utils.gitlab_config(install_webhook=True)])
    def test_install_webhooks(self, mock_post, mock_get):
        get_data = []
        webhook_url = reverse('ci:gitlab:webhook', args=[self.build_user.build_key])
        base = self.server.server_config().get("civet_base_url", "")
        callback_url = "%s%s" % (base, webhook_url)
        get_data.append({'merge_requests_events': 'true', 'push_events': 'true', 'url': 'no_url'})
        mock_get.return_value = utils.Response(get_data)
        mock_post.return_value = utils.Response({'errors': 'error'}, status_code=404)

        # with this data it should try to install the hook but there is an error
        api = self.server.api()
        with self.assertRaises(GitException):
            api.install_webhooks(self.build_user, self.repo)

        # with this data it should do the hook
        mock_post.return_value = utils.Response()
        api.install_webhooks(self.build_user, self.repo)

        # with this data the hook already exists
        get_data.append({'merge_requests_events': 'true',
            'push_events': 'true', 'url': callback_url })
        api.install_webhooks(self.build_user, self.repo)

        with self.settings(INSTALLED_GITSERVERS=[utils.gitlab_config(install_webhook=False)]):
            # this should just return
            api = self.server.api()
            mock_get.call_count = 0
            api.install_webhooks(self.build_user, self.repo)
            self.assertEqual(mock_get.call_count, 0)

    @patch.object(requests, 'post')
    def test_pr_comment(self, mock_post):
        # no real state that we can check, so just go for coverage
        with self.settings(INSTALLED_GITSERVERS=[utils.gitlab_config(remote_update=True)]):
            mock_post.return_value = utils.Response(json_data="some json")
            api = self.server.api()
            # valid post
            api.pr_comment('url', 'message')

            # bad post
            mock_post.side_effect = Exception("BAM!")
            api.pr_comment('url', 'message')

        # should just return
        api.pr_comment('url', 'message')

    @patch.object(requests, 'post')
    def test_update_status(self, mock_post):
        mock_post.return_value = utils.Response()
        ev = utils.create_event(user=self.build_user)
        pr = utils.create_pr(server=self.server)
        ev.pull_request = pr
        ev.save()
        # no state is set so just run for coverage
        with self.settings(INSTALLED_GITSERVERS=[utils.gitlab_config(remote_update=True)]):
            mock_post.return_value = utils.Response(status_code=200, content="some content")
            api = self.server.api()
            api.update_status(ev.base,
                    ev.head, api.PENDING, 'event', 'desc', 'context', api.STATUS_JOB_STARTED)
            self.assertEqual(mock_post.call_count, 1)

            api.update_status(ev.base,
                    ev.head, api.PENDING, 'event', 'desc', 'context', api.STATUS_CONTINUE_RUNNING)
            self.assertEqual(mock_post.call_count, 1)

            # Not updated
            api.update_status(ev.base,
                    ev.head, api.PENDING, 'event', 'desc', 'context', api.STATUS_START_RUNNING)
            self.assertEqual(mock_post.call_count, 1)

            mock_post.return_value = utils.Response(json_data={"error": "some error"},
                    status_code=404)
            api.update_status(ev.base,
                    ev.head, api.PENDING, 'event', 'desc', 'context', api.STATUS_JOB_STARTED)
            self.assertEqual(mock_post.call_count, 2)

            mock_post.return_value = utils.Response(json_data={"error": "some error"},
                    status_code=205)
            api.update_status(ev.base,
                    ev.head, api.PENDING, 'event', 'desc', 'context', api.STATUS_JOB_STARTED)
            self.assertEqual(mock_post.call_count, 3)

            mock_post.side_effect = Exception('BAM!')
            api.update_status(ev.base,
                    ev.head, api.PENDING, 'event', 'desc', 'context', api.STATUS_JOB_STARTED)
            self.assertEqual(mock_post.call_count, 4)

        # This should just return
        api = self.server.api()
        api.update_status(ev.base,
                ev.head, api.PENDING, 'event', 'desc', 'context', api.STATUS_JOB_STARTED)
        self.assertEqual(mock_post.call_count, 4)

    def test_status_str(self):
        api = self.server.api()
        self.assertEqual(api._status_str(api.SUCCESS), 'success')
        self.assertEqual(api._status_str(1000), None)

    @patch.object(requests, 'get')
    def test_get_pr_changed_files(self, mock_get):
        api = self.server.api()
        pr = utils.create_pr(repo=self.repo)
        mock_get.return_value = utils.Response({"changes": []})
        files = api._get_pr_changed_files(self.repo.user.name, self.repo.name, pr.number)
        # shouldn't be any files
        self.assertEqual(len(files), 0)

        file_json = self.get_json_file("files.json")
        file_data = json.loads(file_json)
        mock_get.return_value = utils.Response(file_data)
        files = api._get_pr_changed_files(self.repo.user.name, self.repo.name, pr.number)
        self.assertEqual(["other/path/to/file1", "path/to/file0"], files)

        # simulate a bad request
        mock_get.return_value = utils.Response(file_data, status_code=400)
        files = api._get_pr_changed_files(self.repo.user.name, self.repo.name, pr.number)
        self.assertEqual(files, [])

        # simulate a request timeout
        mock_get.side_effect = Exception("Bam!")
        files = api._get_pr_changed_files(self.repo.user.name, self.repo.name, pr.number)
        self.assertEqual(files, [])

    @patch.object(requests, 'get')
    def test_get_project_access_level(self, mock_get):
        # Can't get user information
        api = self.server.api()
        empty_response = utils.Response({})
        mock_get.return_value = empty_response
        path_with_namespace = '%s/%s' % (self.repo.user.name, self.repo.name)
        level = api._get_project_access_level(path_with_namespace)
        self.assertEqual(level, "Unknown")

        user_json = self.get_json_file("user.json")
        user_data = json.loads(user_json)

        mock_get.return_value = None
        namespace_data = {"namespace": {"id": 999}}
        user_response = utils.Response(user_data)
        bad_response = utils.Response({}, status_code=400)
        namespace_response = utils.Response(namespace_data)

        # Got user information but failed to get member information
        # Then failed to get namespace information
        mock_get.side_effect = [user_response, bad_response, bad_response]
        level = api._get_project_access_level(path_with_namespace)
        self.assertEqual(level, "Unknown")

        # Got user information but failed to get member information
        # Then got namespace information but failed to get member information
        mock_get.side_effect = [user_response, bad_response, namespace_response, bad_response]
        level = api._get_project_access_level(path_with_namespace)
        self.assertEqual(level, "Unknown")

        members_json = self.get_json_file("project_member.json")
        members_data = json.loads(members_json)
        members_response = utils.Response(members_data)

        # Got user information but failed to get member information
        # Then got namespace information and group information
        mock_get.side_effect = [user_response, bad_response, namespace_response, members_response]
        level = api._get_project_access_level(path_with_namespace)
        self.assertEqual(level, "Reporter")

        # Got user information and user is a member
        mock_get.side_effect = [user_response, members_response]
        level = api._get_project_access_level(path_with_namespace)
        self.assertEqual(level, "Reporter")

        # Make sure differenct access levels work
        members_data["access_level"] = 30
        mock_get.side_effect = [user_response, utils.Response(members_data)]
        level = api._get_project_access_level(path_with_namespace)
        self.assertEqual(level, "Developer")

        mock_get.side_effect = Exception("Bam!")
        level = api._get_project_access_level(path_with_namespace)
        self.assertEqual(level, "Unknown")

    @patch.object(requests, 'get')
    def test_get_pr_comments(self, mock_get):
        # bad response, should return empty list
        mock_get.return_value = utils.Response(status_code=400)
        comment_re = r"^some message"
        api = self.server.api()
        ret = api.get_pr_comments("some_url", self.build_user.name, comment_re)
        self.assertEqual(mock_get.call_count, 1)
        self.assertEqual(ret, [])

        c0 = {"author": {"username": self.build_user.name}, "body": "some message", "id": 1}
        c1 = {"author": {"username": self.build_user.name}, "body": "other message", "id": 1}
        c2 = {"author": {"username": "nobody"}, "body": "some message", "id": 1}
        mock_get.return_value = utils.Response(json_data=[c0, c1, c2])

        ret = api.get_pr_comments("some_url", self.build_user.name, comment_re)
        self.assertEqual(ret, [c0]) # the RE only matched 1 of them

    @patch.object(requests, 'delete')
    def test_remove_pr_comment(self, mock_del):
        # should just return
        api = self.server.api()
        api.remove_pr_comment(None)
        self.assertEqual(mock_del.call_count, 0)

        with self.settings(INSTALLED_GITSERVERS=[utils.gitlab_config(remote_update=True)]):
            comment = {"url": "some_url"}
            api = self.server.api()
            # bad response
            mock_del.return_value = utils.Response(status_code=400)
            api.remove_pr_comment(comment)
            self.assertEqual(mock_del.call_count, 1)

            # good response
            mock_del.return_value = utils.Response()
            api.remove_pr_comment(comment)
            self.assertEqual(mock_del.call_count, 2)

    @patch.object(requests, 'put')
    def test_edit_pr_comment(self, mock_edit):
        # should just return
        api = self.server.api()
        api.edit_pr_comment(None, None)
        self.assertEqual(mock_edit.call_count, 0)

        with self.settings(INSTALLED_GITSERVERS=[utils.gitlab_config(remote_update=True)]):
            comment = {"url": "some_url"}
            api = self.server.api()
            # bad response
            mock_edit.return_value = utils.Response(status_code=400)
            api.edit_pr_comment(comment, "new msg")
            self.assertEqual(mock_edit.call_count, 1)

            # good response
            mock_edit.return_value = utils.Response()
            api.edit_pr_comment(comment, "new msg")
            self.assertEqual(mock_edit.call_count, 2)

    @patch.object(requests, 'get')
    def test_is_member(self, mock_get):
        # Username should match
        api = self.server.api()
        ret = api.is_member(self.build_user.name, self.build_user)
        self.assertTrue(ret)

        # Is a member
        mock_get.return_value = utils.Response([{'username': self.build_user.name}])
        ret = api.is_member("foo", self.build_user)
        self.assertIs(ret, True)

        # Not a member
        mock_get.return_value = utils.Response([{'username': "not_username"}])
        ret = api.is_member("foo", self.build_user)
        self.assertIs(ret, False)

    def test_unimplemented(self):
        """
        Just get coverage on the warning messages for the unimplementd functions
        """
        api = self.server.api()
        api.add_pr_label(None, None, None)
        api.remove_pr_label(None, None, None)
        api.pr_review_comment(None, None, None, None, None)
        api.automerge(None, None)

    @patch.object(requests, 'get')
    def test_get_open_prs(self, mock_get):
        repo = utils.create_repo(server=self.server)
        api = self.server.api()
        pr0 = {"title": "some title", "iid": 123, "web_url": "some url"}
        pr0_ret = {"title": "some title", "number": 123, "html_url": "some url"}
        mock_get.return_value = utils.Response([pr0])
        prs = api.get_open_prs(repo.user.name, repo.name)
        self.assertEqual([pr0_ret], prs)

        mock_get.side_effect = Exception("BAM!")
        prs = api.get_open_prs(repo.user.name, repo.name)
        self.assertEqual(prs, None)

    @patch.object(requests, 'put')
    @patch.object(requests, 'get')
    @patch.object(OAuth2Session, 'put')
    @patch.object(OAuth2Session, 'post')
    @patch.object(OAuth2Session, 'get')
    def test_create_or_update_issue(self, mock_get, mock_post, mock_put, mock_rget, mock_rput):
        with self.settings(INSTALLED_GITSERVERS=[utils.gitlab_config(remote_update=True)]):
            get_data = [{"title": "foo", "iid": 1}]
            mock_get.return_value = utils.Response(get_data)
            mock_post.return_value = utils.Response({"web_url": "<some url>"})
            mock_put.return_value = utils.Response({"web_url": "<some url>"})
            api = self.build_user.api()
            # No existing issue, so create it creates a new one
            api.create_or_update_issue(self.repo.user.name,
                    self.repo.name, "Some title", "Some body", False)
            self.assertEqual(mock_get.call_count, 1)
            self.assertEqual(mock_post.call_count, 1)
            self.assertEqual(mock_put.call_count, 0)
            self.assertEqual(api.errors(), [])

            get_data.append({"title": "Some title", "iid": 2})
            mock_get.call_count = 0
            mock_post.call_count = 0
            # An existing issue, so just update it
            api.create_or_update_issue(self.repo.user.name,
                    self.repo.name, "Some title", "Some body", False)
            self.assertEqual(mock_get.call_count, 1)
            self.assertEqual(mock_post.call_count, 0)
            self.assertEqual(mock_put.call_count, 1)
            self.assertEqual(api.errors(), [])

            # An existing issue, but want a new comment
            mock_get.call_count = 0
            mock_put.call_count = 0
            api.create_or_update_issue(self.repo.user.name,
                    self.repo.name, "Some title", "Some body", True)
            self.assertEqual(mock_get.call_count, 1)
            self.assertEqual(mock_post.call_count, 1)
            self.assertEqual(mock_put.call_count, 0)
            self.assertEqual(api.errors(), [])

            mock_get.call_count = 0
            mock_put.call_count = 0
            mock_post.call_count = 0
            # API doesn't have a user, no problem
            api = self.server.api()
            mock_rget.return_value = utils.Response(get_data)
            mock_rput.return_value = utils.Response({"web_url": "<some url>"})
            api.create_or_update_issue(self.repo.user.name,
                    self.repo.name, "Some title", "Some body", False)
            self.assertEqual(mock_get.call_count, 0)
            self.assertEqual(mock_post.call_count, 0)
            self.assertEqual(mock_put.call_count, 0)
            self.assertEqual(mock_rget.call_count, 1)
            self.assertEqual(mock_rput.call_count, 1)

        api = self.build_user.api()
        mock_get.call_count = 0
        mock_put.call_count = 0
        # remote_update=False so nothing happens
        api.create_or_update_issue(self.repo.user.name,
                self.repo.name, "Some title", "Some body", False)
        self.assertEqual(mock_get.call_count, 0)
        self.assertEqual(mock_post.call_count, 0)
        self.assertEqual(mock_put.call_count, 0)
