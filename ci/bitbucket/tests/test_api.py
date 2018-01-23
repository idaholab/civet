
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

from __future__ import unicode_literals
from django.test import TestCase, Client
from django.urls import reverse
from django.test.client import RequestFactory
from django.conf import settings
from django.test import override_settings
from ci.tests import utils
from ci.git_api import GitException
from mock import patch
import requests
import os
try:
    from urllib.parse import urljoin
except ImportError:
    from urlparse import urljoin

@override_settings(INSTALLED_GITSERVERS=[utils.bitbucket_config()])
class Tests(TestCase):
    def setUp(self):
        self.client = Client()
        self.factory = RequestFactory()
        self.server = utils.create_git_server(host_type=settings.GITSERVER_BITBUCKET)
        self.user = utils.create_user_with_token(server=self.server)
        utils.simulate_login(self.client.session, self.user)
        self.gapi = self.server.api()

    def get_json_file(self, filename):
        dirname, fname = os.path.split(os.path.abspath(__file__))
        with open(dirname + '/' + filename, 'r') as f:
            js = f.read()
            return js

    @patch.object(requests, 'get')
    def test_misc(self, mock_get):
        mock_get.return_value = utils.Response()
        api = self.server.api(token="1234")
        api.sign_in_url()
        api.branch_html_url("owner", "repo", "branch")
        api.create_or_update_issue("owner", "repo", "title", "body")

    @patch.object(requests, 'get')
    def test_get_repos(self, mock_get):
        mock_get.return_value = utils.Response(json_data={'message': 'message'}, status_code=404)
        repos = self.gapi.get_repos(self.client.session)
        # shouldn't be any repos
        self.assertEqual(len(repos), 0)

        repo1 = {'owner': self.user.name, 'name': 'repo1'}
        repo2 = {'owner': self.user.name, 'name': 'repo2'}
        mock_get.return_value = utils.Response(json_data=[repo1, repo2])
        repos = self.gapi.get_repos(self.client.session)
        self.assertEqual(len(repos), 2)

        session = self.client.session
        session[self.gapi._repos_key] = ['newrepo1']
        session[self.gapi._org_repos_key] = ['org/repo1']
        session.save()
        repos = self.gapi.get_repos(self.client.session)
        self.assertEqual(len(repos), 1)
        self.assertEqual(repos[0], 'newrepo1')

    @patch.object(requests, 'get')
    def test_get_user_repos(self, mock_get):
        owner, org = self.gapi._get_user_repos(None)
        self.assertEqual(owner, [])
        self.assertEqual(org, [])

        mock_get.return_value = utils.Response(json_data={'message': 'message'}, status_code=404)
        owner, org = self.gapi._get_user_repos(self.user.name)
        self.assertEqual(owner, [])
        self.assertEqual(org, [])

        repo1 = {'owner': self.user.name, 'name': 'repo1'}
        repo2 = {'owner': 'org', 'name': 'repo2'}
        mock_get.return_value = utils.Response(json_data=[repo1, repo2])
        owner, org = self.gapi._get_user_repos(self.user.name)
        self.assertEqual(owner, ["%s/repo1" % self.user.name])
        self.assertEqual(org, ["org/repo2"])

    @patch.object(requests, 'get')
    def test_get_all_repos(self, mock_get):
        mock_get.return_value = utils.Response(json_data={'message': 'message'}, status_code=404)
        repos = self.gapi.get_all_repos(self.user.name)
        # shouldn't be any repos
        self.assertEqual(len(repos), 0)

        mock_get.return_value = utils.Response(json_data=[
          {'owner': self.user.name, 'name': 'repo1'},
          {'owner': self.user.name, 'name': 'repo2'},
          {'owner': "other", 'name': 'repo1'},
          {'owner': "other", 'name': 'repo2'},
          ])
        repos = self.gapi.get_all_repos(self.user.name)
        self.assertEqual(len(repos), 4)

    @patch.object(requests, 'get')
    def test_get_branches(self, mock_get):
        repo = utils.create_repo(user=self.user)
        mock_get.return_value = utils.Response(json_data={})
        branches = self.gapi.get_branches(self.user, repo)
        # shouldn't be any branch
        self.assertEqual(len(branches), 0)

        mock_get.return_value = utils.Response(json_data={'branch1': 'info', 'branch2': 'info'})
        branches = self.gapi.get_branches(self.user, repo)
        self.assertEqual(len(branches), 2)

    @patch.object(requests, 'get')
    def test_is_collaborator(self, mock_get):
        repo = utils.create_repo(user=self.user)
        # user is repo owner
        ret = self.gapi.is_collaborator(self.user, repo)
        self.assertIs(ret, True)
        user2 = utils.create_user('user2', server=self.server)
        repo = utils.create_repo(user=user2)
        # a collaborator
        mock_get.return_value = utils.Response(json_data={'values': [{'name': repo.name}]}, status_code=200)
        ret = self.gapi.is_collaborator(self.user, repo)
        self.assertIs(ret, True)
        # not a collaborator
        mock_get.return_value = utils.Response(status_code=404)
        ret = self.gapi.is_collaborator(self.user, repo)
        self.assertIs(ret, False)

    @patch.object(requests, 'get')
    def test_last_sha(self, mock_get):
        branch = utils.create_branch(user=self.user)
        mock_get.return_value = utils.Response(json_data={branch.name: {'raw_node': '123'}})
        sha = self.gapi.last_sha(self.user.name, branch.repository.name, branch.name)
        self.assertEqual(sha, '123')

        mock_get.return_value = utils.Response({})
        sha = self.gapi.last_sha(self.user.name, branch.repository.name, branch.name)
        self.assertEqual(sha, None)

        mock_get.side_effect = Exception("Bam!")
        sha = self.gapi.last_sha(self.user.name, branch.repository.name, branch.name)
        self.assertEqual(sha, None)

    @patch.object(requests, 'get')
    @patch.object(requests, 'post')
    def test_install_webhooks(self, mock_post, mock_get):
        repo = utils.create_repo(user=self.user)
        event0 = {'events': ['pullrequest:created', 'repo:push'], 'url': 'no_url'}
        event1 = {'events': ['pullrequest:created', 'repo:other_action'], 'url': 'no_url'}
        get_data = {'values': [event0, event1]}
        callback_url = urljoin(self.gapi._civet_url, reverse('ci:bitbucket:webhook', args=[self.user.build_key]))

        with self.settings(INSTALLED_GITSERVERS=[utils.bitbucket_config(install_webhook=True)]):
            api = self.server.api()
            # Failed to do an the initial get
            mock_get.return_value = utils.Response(status_code=404)
            with self.assertRaises(GitException):
                api.install_webhooks(self.user, repo)
            self.assertEqual(mock_get.call_count, 1)
            self.assertEqual(mock_post.call_count, 0)

            # with this data it should try to install the hook but there is an error
            mock_get.return_value = utils.Response(json_data=get_data)
            mock_post.return_value = utils.Response(json_data={}, status_code=404)
            mock_get.call_count = 0
            with self.assertRaises(GitException):
                api.install_webhooks(self.user, repo)
            self.assertEqual(mock_get.call_count, 1)
            self.assertEqual(mock_post.call_count, 1)

            # with this data it should do the hook
            mock_get.call_count = 0
            mock_post.call_count = 0
            mock_post.return_value = utils.Response(json_data={}, status_code=201)
            api.install_webhooks(self.user, repo)
            self.assertEqual(mock_get.call_count, 1)
            self.assertEqual(mock_post.call_count, 1)

            # with this data the hook already exists
            mock_get.call_count = 0
            mock_post.call_count = 0
            get_data['values'][0]['url'] = callback_url
            api.install_webhooks(self.user, repo)
            self.assertEqual(mock_get.call_count, 1)
            self.assertEqual(mock_post.call_count, 0)

        # this should just return
        mock_get.call_count = 0
        mock_post.call_count = 0
        self.gapi.install_webhooks(self.user, repo)
        self.assertEqual(mock_get.call_count, 0)
        self.assertEqual(mock_post.call_count, 0)

    @patch.object(requests, 'post')
    def test_pr_comment(self, mock_post):
        # no real state that we can check, so just go for coverage
        with self.settings(INSTALLED_GITSERVERS=[utils.bitbucket_config(remote_update=True)]):
            mock_post.return_value = utils.Response(status_code=200)
            api = self.server.api()
            # valid post
            api.pr_comment('url', 'message')
            self.assertEqual(mock_post.call_count, 1)

            # bad post
            mock_post.return_value = utils.Response(status_code=400, json_data={'message': 'bad post'})
            api.pr_comment('url', 'message')
            self.assertEqual(mock_post.call_count, 2)

            # bad post
            mock_post.side_effect = Exception("Bam!")
            api.pr_comment('url', 'message')
            self.assertEqual(mock_post.call_count, 3)

        # should just return
        mock_post.call_count = 0
        self.gapi.pr_comment('url', 'message')
        self.assertEqual(mock_post.call_count, 0)

    @patch.object(requests, 'get')
    def test_get_open_prs(self, mock_get):
        repo = utils.create_repo(server=self.server)
        api = self.server.api()
        pr0 = {"title": "some title", "id": 123, "links": {"html": "some url"}}
        pr0_ret = {"title": "some title", "number": 123, "html_url": "some url"}
        mock_get.return_value = utils.Response({"values":[pr0]})
        prs = api.get_open_prs(repo.user.name, repo.name)
        self.assertEqual([pr0_ret], prs)

        mock_get.side_effect = Exception("BAM!")
        prs = api.get_open_prs(repo.user.name, repo.name)
        self.assertEqual(prs, None)

    def test_unimplemented(self):
        """
        Just get coverage on the warning messages for the unimplementd functions
        """
        self.gapi.add_pr_label(None, None, None, None)
        self.gapi.remove_pr_label(None, None, None, None)
        self.gapi.get_pr_comments(None, None, None)
        self.gapi.remove_pr_comment(None)
        self.gapi.edit_pr_comment(None, None)
        self.gapi.is_member(None, None)
        self.gapi.pr_review_comment(None, None)
        self.gapi.update_pr_status(None, None, None, None, None, None, None)
