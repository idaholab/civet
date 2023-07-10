
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
from django.test import override_settings
import requests
from ci.tests import utils
from ci.git_api import GitException
from mock import patch
import os, json
from ci.tests import DBTester
from requests_oauthlib import OAuth2Session

@override_settings(INSTALLED_GITSERVERS=[utils.github_config()])
class Tests(DBTester.DBTester):
    def setUp(self):
        super(Tests, self).setUp()
        self.create_default_recipes()
        utils.simulate_login(self.client.session, self.build_user)
        self.auth = self.build_user.server.auth().start_session_for_user(self.build_user)

    def get_json_file(self, filename):
        dirname, fname = os.path.split(os.path.abspath(__file__))
        with open(dirname + '/' + filename, 'r') as f:
            js = f.read()
            return js

    def test_status_str(self):
        api = self.server.api(token="1234")
        self.assertEqual(api._status_str(api.SUCCESS), 'success')
        self.assertEqual(api._status_str(1000), None)

    def test_urls(self):
        api = self.server.api()
        api.sign_in_url()
        api.branch_html_url("owner", "repo", "branch")
        api.repo_html_url("owner", "repo")
        api.commit_html_url("owner", "repo", "sha")

    def test_api_type(self):
        self.assertEqual(self.server.api_type(), 'GitHub')

    def test_can_view_repo(self):
        api = self.server.api()
        api._api_url = 'https://api.github.com'

        civet_exists = api.can_view_repo('idaholab', 'civet')
        self.assertTrue(civet_exists)

        bad_repo_exists = api.can_view_repo('foobar123', 'bazbang456')
        self.assertFalse(bad_repo_exists)

    @patch.object(requests, 'get')
    def test_get_repos(self, mock_get):
        mock_get.return_value = utils.Response(status_code=200)
        api = self.server.api()
        repos = api.get_repos(self.client.session)
        # shouldn't be any repos
        self.assertEqual(len(repos), 0)
        self.assertEqual(mock_get.call_count, 1)

        repo1 = {'name': 'repo1', 'owner': {'login': 'owner'} }
        repo2 = {'name': 'repo2', 'owner': {'login': 'owner'}}
        mock_get.return_value = utils.Response([repo1, repo2])
        repos = api.get_repos(self.client.session)
        self.assertEqual(mock_get.call_count, 2)
        self.assertEqual(len(repos), 2)

        # Check to make sure the cache works
        session = self.client.session
        cached_repos = ['owner/repo1']
        session[api._repos_key] = cached_repos
        session.save()
        repos = api.get_repos(self.client.session)
        self.assertEqual(mock_get.call_count, 2)
        self.assertEqual(cached_repos, repos)

    @patch.object(requests, 'get')
    def test_get_all_repos(self, mock_get):
        mock_get.return_value = utils.Response(status_code=200)
        api = self.server.api()

        # shouldn't be any repos
        repos = api.get_all_repos(self.build_user.name)
        self.assertEqual(mock_get.call_count, 2) # 1 for user repos, 1 for org repos
        self.assertEqual(len(repos), 0)

        # We should now have repos
        repo1 = {'name': 'repo1', 'owner': {'login': 'owner'} }
        repo2 = {'name': 'repo2', 'owner': {'login': 'owner'}}
        mock_get.return_value = utils.Response([repo1, repo2])
        repos = api.get_all_repos(self.build_user.name)
        self.assertEqual(mock_get.call_count, 4)
        self.assertEqual(len(repos), 4)

    @patch.object(requests, 'get')
    def test_get_branches(self, mock_get):
        mock_get.return_value = utils.Response(status_code=200)
        api = self.server.api()

        # shouldn't be any branch
        branches = api.get_branches(self.owner, self.repo)
        self.assertEqual(len(branches), 0)
        self.assertEqual(mock_get.call_count, 1)

        mock_get.return_value = utils.Response([{'name': 'branch1'}, {'name': 'branch2'}])
        branches = api.get_branches(self.owner, self.repo)
        self.assertEqual(mock_get.call_count, 2)
        self.assertEqual(len(branches), 2)

    @patch.object(requests, 'post')
    @patch.object(requests, 'get')
    def test_update_pr_status(self, mock_get, mock_post):
        mock_get.side_effect = Exception("Update PR status shouldn't be doing a GET")
        ev = utils.create_event(user=self.build_user)
        pr = utils.create_pr()
        ev.pull_request = pr
        ev.save()
        # no state is set so just run for coverage
        with self.settings(INSTALLED_GITSERVERS=[utils.github_config(remote_update=True)]):
            mock_post.return_value = utils.Response(status_code=404)
            api = self.server.api()
            api.update_pr_status(ev.base,
                    ev.head, api.PENDING, 'event', 'desc', 'context', api.STATUS_JOB_STARTED)
            self.assertEqual(mock_get.call_count, 0)
            self.assertEqual(mock_post.call_count, 1)
            self.assertNotEqual(api.errors(), [])

            api = self.server.api()
            mock_post.return_value = utils.Response()
            api.update_pr_status(ev.base,
                    ev.head, api.PENDING, 'event', 'desc', 'context', api.STATUS_JOB_STARTED)
            self.assertEqual(mock_get.call_count, 0)
            self.assertEqual(mock_post.call_count, 2)
            self.assertEqual(api.errors(), [])

            mock_post.side_effect = Exception('BAM!')
            api.update_pr_status(ev.base,
                    ev.head, api.PENDING, 'event', 'desc', 'context', api.STATUS_JOB_STARTED)
            self.assertEqual(mock_get.call_count, 0)
            self.assertEqual(mock_post.call_count, 3)
            self.assertEqual(len(api.errors()), 1)

        # This should just return
        api = self.server.api()
        mock_post.call_count = 0
        api.update_pr_status(ev.base,
                ev.head, api.PENDING, 'event', 'desc', 'context', api.STATUS_JOB_STARTED)
        self.assertEqual(mock_get.call_count, 0)
        self.assertEqual(mock_post.call_count, 0)
        self.assertEqual(api.errors(), [])

    @patch.object(requests, 'get')
    def test_is_collaborator(self, mock_get):
        # user is repo owner
        mock_get.return_value = utils.Response()
        api = self.server.api()
        self.assertTrue(api.is_collaborator(self.owner, self.repo))

        user2 = utils.create_user('user2')
        repo = utils.create_repo(user=user2)
        # a collaborator
        mock_get.return_value = utils.Response(status_code=204)
        self.assertTrue(api.is_collaborator(self.build_user, repo))
        self.assertEqual(api.errors(), [])

        # not a collaborator
        api = self.server.api()
        mock_get.return_value = utils.Response(status_code=404)
        self.assertFalse(api.is_collaborator(self.build_user, repo))
        self.assertEqual(len(api.errors()), 1)

        # doesn't have permission to check collaborator
        api = self.server.api()
        mock_get.return_value = utils.Response(status_code=403)
        self.assertFalse(api.is_collaborator(self.build_user, repo))
        self.assertEqual(len(api.errors()), 1)

        # some other response code
        api = self.server.api()
        mock_get.return_value = utils.Response(status_code=405)
        self.assertFalse(api.is_collaborator(self.build_user, repo))
        self.assertNotEqual(api.errors(), [])

        # error occurred
        api = self.server.api()
        mock_get.side_effect = Exception("BAM!")
        self.assertFalse(api.is_collaborator(self.build_user, repo))
        self.assertNotEqual(api.errors(), [])

    class ShaResponse(utils.Response):
        def __init__(self, commit=True, *args, **kwargs):
            utils.Response.__init__(self, *args, **kwargs)
            if commit:
                self.json_data = {"commit": {"sha": "123"}}
            else:
                self.json_data = None

    @patch.object(requests, 'get')
    def test_last_sha(self, mock_get):
        mock_get.return_value = self.ShaResponse(True)
        api = self.server.api()
        sha = api.last_sha(self.build_user.name, self.branch.repository.name, self.branch.name)
        self.assertEqual(sha, '123')
        self.assertEqual(api.errors(), [])

        api = self.server.api()
        mock_get.return_value = self.ShaResponse(False)
        sha = api.last_sha(self.build_user, self.branch.repository.name, self.branch.name)
        self.assertEqual(sha, None)
        self.assertEqual(len(api.errors()), 1)

        api = self.server.api()
        mock_get.side_effect = Exception("BAM!")
        sha = api.last_sha(self.build_user, self.branch.repository.name, self.branch.name)
        self.assertEqual(sha, None)
        # 1 for the bad response and 1 for the error message
        self.assertEqual(len(api.errors()), 2)

    @patch.object(requests, 'get')
    def test_tag_sha(self, mock_get):
        jdata = [{"name": "tagname",
                "commit": {"sha": "123"},
                }]
        mock_get.return_value = utils.Response(jdata)
        api = self.server.api()
        sha = api._tag_sha(self.build_user.name, self.branch.repository.name, "tagname")
        self.assertEqual(sha, '123')
        self.assertEqual(api.errors(), [])

        jdata[0]["name"] = "othertag"
        api = self.server.api()
        mock_get.return_value = utils.Response(jdata)
        sha = api._tag_sha(self.build_user, self.branch.repository.name, "tagname")
        self.assertEqual(sha, None)
        self.assertEqual(len(api.errors()), 1)

        api = self.server.api()
        mock_get.side_effect = Exception("BAM!")
        sha = api._tag_sha(self.build_user, self.branch.repository.name, "tagname")
        self.assertEqual(sha, None)
        # 1 for the bad response and 1 for the error message
        self.assertEqual(len(api.errors()), 2)

    @patch.object(requests, 'get')
    @patch.object(requests, 'post')
    @override_settings(INSTALLED_GITSERVERS=[utils.github_config(install_webhook=True)])
    def test_install_webhooks(self, mock_post, mock_get):
        get_data = []
        base = self.server.server_config().get("civet_base_url", "")
        callback_url = "%s%s" % (base, reverse('ci:github:webhook', args=[self.build_user.build_key]))
        get_data.append({'events': ['push'], 'config': {'url': 'no_url', 'content_type': 'json'}})
        get_data.append({'events': ['pull_request'],
            'config': {'url': 'no_url', 'content_type': 'json'}})

        # can't even get the webhooks
        api = self.server.api()
        mock_get.return_value = utils.Response(get_data, status_code=400)
        mock_post.return_value = utils.Response({'errors': 'error'})
        with self.assertRaises(GitException):
            api.install_webhooks(self.build_user, self.repo)
        self.assertEqual(len(api.errors()), 2)

        # got the webhooks, none are valid, error trying to install
        api = self.server.api()
        get_data.append({'events': [], 'config': {'url': 'no_url', 'content_type': 'json'}})
        mock_get.return_value = utils.Response(get_data, status_code=200)
        with self.assertRaises(GitException):
            api.install_webhooks(self.build_user, self.repo)
        self.assertEqual(len(api.errors()), 0)

        # bad status code when trying to post
        api = self.server.api()
        mock_post.return_value = utils.Response({'errors': 'error'}, status_code=404)
        with self.assertRaises(GitException):
            api.install_webhooks(self.build_user, self.repo)
        self.assertEqual(len(api.errors()), 1)

        # with this data it should do the hook
        api = self.server.api()
        get_data.append({'events': ['pull_request', 'push'],
            'config': {'url': 'no_url', 'content_type': 'json'}})
        mock_post.return_value = utils.Response({})
        api.install_webhooks(self.build_user, self.repo)
        self.assertEqual(len(api.errors()), 0)

        # with this data the hook already exists
        mock_get.call_count = 0
        mock_post.call_count = 0
        api = self.server.api()
        get_data.append({'events': ['pull_request', 'push'],
            'config': {'url': callback_url, 'content_type': 'json'}})
        api.install_webhooks(self.build_user, self.repo)
        self.assertEqual(len(api.errors()), 0)
        self.assertEqual(mock_get.call_count, 1)
        self.assertEqual(mock_post.call_count, 0)

        with self.settings(INSTALLED_GITSERVERS=[utils.github_config(install_webhook=False)]):
            # this should just return
            api = self.server.api()
            mock_get.call_count = 0
            api.install_webhooks(self.build_user, self.repo)
            self.assertEqual(mock_get.call_count, 0)

    @patch.object(requests, 'get')
    @patch.object(requests, 'delete')
    def test_remove_pr_todo_labels(self, mock_del, mock_get):
        prefix = self.server.server_config()["remove_pr_label_prefix"][0]
        data = [{"name": "%s Address Comments" % prefix}, {"name": "Other"}]
        mock_get.return_value = utils.Response(data)
        mock_del.return_value = utils.Response({})
        with self.settings(INSTALLED_GITSERVERS=[utils.github_config(remote_update=True)]):
            # We can't really test this very well, so just try to get some coverage
            api = self.server.api()
            mock_get.return_value = utils.Response()
            mock_del.return_value = utils.Response({})

            # no labels
            api._remove_pr_todo_labels(self.build_user.name, self.repo.name, 1)
            self.assertEqual(mock_get.call_count, 1)
            self.assertEqual(mock_del.call_count, 0)

            # The title has the remove prefix so it would get deleted
            mock_get.call_count = 0
            mock_get.return_value = utils.Response(data)
            api._remove_pr_todo_labels(self.build_user.name, self.repo.name, 1)
            self.assertEqual(mock_get.call_count, 1)
            self.assertEqual(mock_del.call_count, 1)

            # The title has the remove prefix but the request raised an exception
            mock_del.return_value = utils.Response({}, do_raise=True)
            mock_get.call_count = 0
            mock_del.call_count = 0
            api._remove_pr_todo_labels(self.build_user.name, self.repo.name, 1)
            self.assertEqual(mock_get.call_count, 1)
            self.assertEqual(mock_del.call_count, 1)

            # The title doesn't have the remove prefix
            mock_get.return_value = utils.Response([{"name": "NOT A PREFIX Address Comments"},
                {"name": "Other"}])
            mock_del.return_value = utils.Response({})
            mock_get.call_count = 0
            mock_del.call_count = 0
            api._remove_pr_todo_labels(self.build_user.name, self.repo.name, 1)
            self.assertEqual(mock_get.call_count, 1)
            self.assertEqual(mock_del.call_count, 0)

        # We aren't updating the server
        mock_get.call_count = 0
        mock_del.call_count = 0
        self.server.api()._remove_pr_todo_labels(self.build_user.name, self.repo.name, 1)
        self.assertEqual(mock_get.call_count, 0)
        self.assertEqual(mock_del.call_count, 0)

    @patch.object(requests, 'get')
    @override_settings(INSTALLED_GITSERVERS=[utils.github_config(remote_update=True)])
    def test_get_pr_changed_files(self, mock_get):
        api = self.server.api()
        pr = utils.create_pr(repo=self.repo)
        mock_get.return_value = utils.Response(status_code=200)
        files = api._get_pr_changed_files(self.repo.user.name, self.repo.name, pr.number)
        # shouldn't be any files
        self.assertEqual(len(files), 0)

        file_json = self.get_json_file("files.json")
        file_data = json.loads(file_json)
        mock_get.return_value = utils.Response(file_data)
        files = api._get_pr_changed_files(self.repo.user.name, self.repo.name, pr.number)
        self.assertEqual(len(files), 2)
        self.assertEqual(["other/path/to/file1", "path/to/file0"], files)

        # simulate a bad request
        mock_get.return_value = utils.Response(status_code=400)
        files = api._get_pr_changed_files(self.repo.user.name, self.repo.name, pr.number)
        self.assertEqual(files, [])

        # simulate a request timeout
        mock_get.side_effect = Exception("Bam!")
        files = api._get_pr_changed_files(self.repo.user.name, self.repo.name, pr.number)
        self.assertEqual(files, [])

    @patch.object(requests, 'post')
    def test_add_pr_label(self, mock_post):
        # should just return
        self.server.api().add_pr_label(self.repo, 0, "foo")
        self.assertEqual(mock_post.call_count, 0)

        with self.settings(INSTALLED_GITSERVERS=[utils.github_config(remote_update=True)]):
            pr = utils.create_pr(repo=self.repo)
            mock_post.return_value = utils.Response(status_code=200)

            api = self.server.api()
            # No label, no problem
            api.add_pr_label(self.repo, pr.number, None)
            self.assertEqual(mock_post.call_count, 0)

            # valid label
            api.add_pr_label(self.repo, pr.number, 'foo')
            self.assertEqual(mock_post.call_count, 1)

            # bad response
            mock_post.return_value = utils.Response(status_code=400)
            api.add_pr_label(self.repo, pr.number, 'foo')
            self.assertEqual(mock_post.call_count, 2)

    @patch.object(requests, 'delete')
    def test_remove_pr_label(self, mock_delete):
        # should just return
        self.server.api().remove_pr_label(self.repo, 0, 'foo')
        self.assertEqual(mock_delete.call_count, 0)

        with self.settings(INSTALLED_GITSERVERS=[utils.github_config(remote_update=True)]):
            pr = utils.create_pr(repo=self.repo)
            mock_delete.return_value = utils.Response(status_code=200)
            api = self.server.api()

            # No label, no problem
            api.remove_pr_label(self.repo, pr.number, None)
            self.assertEqual(mock_delete.call_count, 0)

            # valid label
            api.remove_pr_label(self.repo, pr.number, 'foo')
            self.assertEqual(mock_delete.call_count, 1)

            # bad response
            mock_delete.return_value = utils.Response(status_code=400)
            api.remove_pr_label(self.repo, pr.number, 'foo bar')
            self.assertEqual(mock_delete.call_count, 2)

            # 404, label probably isn't there
            mock_delete.return_value = utils.Response(status_code=404)
            api.remove_pr_label(self.repo, pr.number, 'foo')
            self.assertEqual(mock_delete.call_count, 3)

    @patch.object(requests, 'get')
    def test_get_pr_comments(self, mock_get):
        with self.settings(INSTALLED_GITSERVERS=[utils.github_config(remote_update=True)]):
            # bad response, should return empty list
            mock_get.return_value = utils.Response(status_code=400)
            comment_re = r"^some message"
            api = self.server.api()
            ret = api.get_pr_comments("some_url", self.build_user.name, comment_re)
            self.assertEqual(mock_get.call_count, 1)
            self.assertEqual(ret, [])

            c0 = {"user": {"login": self.build_user.name}, "body": "some message"}
            c1 = {"user": {"login": self.build_user.name}, "body": "other message"}
            c2 = {"user": {"login": "nobody"}, "body": "some message"}
            mock_get.return_value = utils.Response(json_data=[c0, c1, c2])

            ret = api.get_pr_comments("some_url", self.build_user.name, comment_re)
            self.assertEqual(ret, [c0])

    @patch.object(requests, 'delete')
    def test_remove_pr_comment(self, mock_del):
        # should just return
        self.server.api().remove_pr_comment(None)
        self.assertEqual(mock_del.call_count, 0)

        with self.settings(INSTALLED_GITSERVERS=[utils.github_config(remote_update=True)]):
            comment = {"url": "some_url"}
            # bad response
            api = self.server.api()
            mock_del.return_value = utils.Response(status_code=400)
            api.remove_pr_comment(comment)
            self.assertEqual(mock_del.call_count, 1)

            # good response
            api = self.server.api()
            mock_del.return_value = utils.Response()
            api.remove_pr_comment(comment)
            self.assertEqual(mock_del.call_count, 2)

    @patch.object(requests, 'patch')
    def test_edit_pr_comment(self, mock_edit):
        # should just return
        self.server.api().edit_pr_comment(None, None)
        self.assertEqual(mock_edit.call_count, 0)

        with self.settings(INSTALLED_GITSERVERS=[utils.github_config(remote_update=True)]):
            comment = {"url": "some_url"}
            api = self.server.api()
            # bad response
            mock_edit.return_value = utils.Response(status_code=400)
            api.edit_pr_comment(comment, "new msg")
            self.assertEqual(mock_edit.call_count, 1)

            # good response
            api = self.server.api()
            mock_edit.return_value = utils.Response()
            api.edit_pr_comment(comment, "new msg")
            self.assertEqual(mock_edit.call_count, 2)

    @patch.object(requests, 'get')
    def test_is_team_member(self, mock_get):
        team_data = {"state": "active"}
        api = self.server.api()
        mock_get.return_value = utils.Response(team_data, status_code=404)
        # Not a member
        is_member = api._is_team_member(100, "username")
        self.assertFalse(is_member)
        self.assertEqual(len(api.errors()), 1) # bad status

        # Is an active member
        api = self.server.api()
        mock_get.return_value = utils.Response(team_data)
        is_member = api._is_team_member(100, "username")
        self.assertTrue(is_member)
        self.assertEqual(len(api.errors()), 0)

        # Is a pending member
        team_data = {"state": "pending"}
        mock_get.return_value = utils.Response(team_data)
        is_member = api._is_team_member(100, "username")
        self.assertFalse(is_member)
        self.assertEqual(len(api.errors()), 0)

        mock_get.side_effect = Exception("Bam!")
        # Bad request
        is_member = api._is_team_member(100, "username")
        self.assertFalse(is_member)
        self.assertEqual(len(api.errors()), 1)

    @patch.object(requests, 'get')
    def test_is_org_member(self, mock_get):
        org_data = {"login": "org"}
        mock_get.return_value = utils.Response([org_data], status_code=404)
        api = self.server.api()
        # Bad response
        is_member = api._is_org_member("org")
        self.assertFalse(is_member)

        # Is a member
        api = self.server.api()
        mock_get.return_value = utils.Response([org_data])
        is_member = api._is_org_member("org")
        self.assertTrue(is_member)

        # Is not a member
        is_member = api._is_org_member("other_org")
        self.assertFalse(is_member)

        mock_get.side_effect = Exception("Bam!")
        # Bad request
        is_member = api._is_org_member("org")
        self.assertFalse(is_member)

    @patch.object(requests, 'get')
    def test_get_team_id(self, mock_get):
        team_data = {"name": "foo", "id": "100"}
        mock_get.return_value = utils.Response([team_data])
        api = self.server.api()
        # No matching team id
        team_id = api._get_team_id("bar", "bar")
        self.assertIsNone(team_id)

        # Matching team id
        team_id = api._get_team_id("bar", "foo")
        self.assertEqual(team_id, "100")

        mock_get.side_effect = Exception("Bam!")
        # Bad call
        team_id = api._get_team_id("bar", "foo")
        self.assertIsNone(team_id)

    @patch.object(requests, 'get')
    # We actually start a session for a user here, unlike other tests
    @patch.object(OAuth2Session, 'get')
    def test_is_member(self, mock_oauth_get, mock_get):
        mock_get.return_value = utils.Response()
        mock_oauth_get.return_value = utils.Response()
        user = utils.create_user_with_token(name="otherUser", server=self.server)
        api = self.server.api()
        # Invalid team name
        is_member = api.is_member("bad/team/name", user)
        self.assertFalse(is_member)
        self.assertEqual(len(api.errors()), 1)
        self.assertEqual(mock_get.call_count, 0)

        # Just a name so interpret as an organization or a user
        org_data = {"login": "org"}
        mock_oauth_get.return_value = utils.Response([org_data])
        is_member = api.is_member("org", user)
        self.assertTrue(is_member)

        # Just the user name
        is_member = api.is_member(user.name, user)
        self.assertTrue(is_member)

        # No match
        is_member = api.is_member("other_org", user)
        self.assertFalse(is_member)

        # Try out the team name route
        team_id_data = {"name": "foo", "id": "100"}
        team_data = {"state": "active"}

        team_id_response = utils.Response([team_id_data])
        team_data_response = utils.Response(team_data)
        mock_get.side_effect = [team_id_response, team_data_response]

        # Correct team
        is_member = api.is_member("bar/foo", user)
        self.assertTrue(is_member)

        # Bad team
        team_data["state"] = "inactive"
        mock_get.side_effect = [team_id_response, team_data_response]
        is_member = api.is_member("bar/foo", user)
        self.assertFalse(is_member)

    @patch.object(requests, 'get')
    def test_get_open_prs(self, mock_get):
        repo = utils.create_repo(server=self.server)
        api = self.server.api()
        pr0 = {"title": "some title", "number": 123, "html_url": "some url"}
        mock_get.return_value = utils.Response([pr0])
        prs = api.get_open_prs(repo.user.name, repo.name)
        self.assertEqual([pr0], prs)

        mock_get.side_effect = Exception("BAM!")
        prs = api.get_open_prs(repo.user.name, repo.name)
        self.assertEqual(prs, None)

    @patch.object(requests, 'post')
    def test_pr_review_comment(self, mock_post):
        with self.settings(INSTALLED_GITSERVERS=[utils.github_config(remote_update=True)]):
            mock_post.return_value = utils.Response()
            api = self.server.api()
            api.pr_review_comment("url", "sha", "filepath", 2, "message")
            self.assertEqual(mock_post.call_count, 1)

        api = self.server.api()
        mock_post.call_count = 0
        api.pr_review_comment("url", "sha", "filepath", 2, "message")
        self.assertEqual(mock_post.call_count, 0)

    @patch.object(OAuth2Session, 'patch')
    @patch.object(OAuth2Session, 'post')
    @patch.object(OAuth2Session, 'get')
    def test_create_or_update_issue(self, mock_get, mock_post, mock_patch):
        with self.settings(INSTALLED_GITSERVERS=[utils.github_config(remote_update=True)]):
            get_data = [{"title": "foo", "number": 1, "comments_url": "<some url>"}]
            mock_get.return_value = utils.Response(get_data)
            mock_post.return_value = utils.Response({"html_url": "<some url>"})
            mock_patch.return_value = utils.Response({"html_url": "<some url>"})
            api = self.build_user.api()
            # No existing issue, so create it creates a new one
            api.create_or_update_issue(self.repo.user.name,
                    self.repo.name, "Some title", "Some body", False)
            self.assertEqual(mock_get.call_count, 1)
            self.assertEqual(mock_post.call_count, 1)
            self.assertEqual(mock_patch.call_count, 0)
            self.assertEqual(api.errors(), [])

            get_data.append({"title": "Some title", "number": 2, "comments_url": "<some url>"})
            mock_get.call_count = 0
            mock_post.call_count = 0
            # An existing issue, so just update it
            api.create_or_update_issue(self.repo.user.name,
                    self.repo.name, "Some title", "Some body", False)
            self.assertEqual(mock_get.call_count, 1)
            self.assertEqual(mock_post.call_count, 0)
            self.assertEqual(mock_patch.call_count, 1)
            self.assertEqual(api.errors(), [])

            mock_get.call_count = 0
            mock_patch.call_count = 0
            # An existing issue, but they want a new comment
            api.create_or_update_issue(self.repo.user.name,
                    self.repo.name, "Some title", "Some body", True)
            self.assertEqual(mock_get.call_count, 1)
            self.assertEqual(mock_post.call_count, 1)
            self.assertEqual(mock_patch.call_count, 0)
            self.assertEqual(api.errors(), [])

            mock_get.call_count = 0
            mock_patch.call_count = 0
            mock_post.call_count = 0
            # API doesn't have a user, so nothing gets called
            api = self.server.api()
            api.create_or_update_issue(self.repo.user.name,
                    self.repo.name, "Some title", "Some body", False)
            self.assertEqual(mock_get.call_count, 0)
            self.assertEqual(mock_post.call_count, 0)
            self.assertEqual(mock_patch.call_count, 0)

        api = self.build_user.api()
        # remote_update=False so nothing happens
        api.create_or_update_issue(self.repo.user.name,
                self.repo.name, "Some title", "Some body", False)
        self.assertEqual(mock_get.call_count, 0)
        self.assertEqual(mock_post.call_count, 0)
        self.assertEqual(mock_patch.call_count, 0)

    @patch.object(requests, 'put')
    @patch.object(requests, 'get')
    def test_automerge(self, mock_get, mock_put):
        mock_get.return_value = utils.Response()
        mock_put.return_value = utils.Response(status_code=403)
        repo = utils.create_repo(server=self.server)
        api = self.server.api()
        self.assertFalse(api.automerge(repo, 1))

        with self.settings(INSTALLED_GITSERVERS=[utils.github_config(remote_update=True)]):
            api = self.server.api()
            # Repo is not configured for auto merge
            self.assertFalse(api.automerge(repo, 1))

        auto_merge_settings = {"auto_merge_label": "Auto Merge",
                "auto_merge_require_review": False,
                "auto_merge_enabled": True,
                }
        repo_settings = {"%s/%s" % (repo.user.name, repo.name): auto_merge_settings}

        pr_data = {"labels": [], "head": {"sha": "1234"}}
        pr_response = utils.Response(json_data=pr_data)
        with self.settings(INSTALLED_GITSERVERS=[
            utils.github_config(remote_update=True, repo_settings=repo_settings)]):

            api = self.server.api()
            # Couldn't get PR data
            self.assertFalse(api.automerge(repo, 1))
            self.assertEqual(mock_put.call_count, 0)

            mock_get.return_value = pr_response
            # Auto merge label not on PR
            self.assertFalse(api.automerge(repo, 1))
            self.assertEqual(mock_put.call_count, 0)

            auto_merge = {"name": auto_merge_settings["auto_merge_label"]}
            other_label = {"name": "other_label_name"}
            pr_data["labels"] = [auto_merge, other_label]
            mock_get.return_value = utils.Response(json_data=pr_data)
            # Should try to auto merge but it failed
            self.assertFalse(api.automerge(repo, 1))
            self.assertEqual(mock_put.call_count, 1)

            mock_put.return_value = utils.Response()
            # Should try to auto merge and succeed
            self.assertTrue(api.automerge(repo, 1))
            self.assertEqual(mock_put.call_count, 2)

        # Enable requiring an approved review
        auto_merge_settings["auto_merge_require_review"] = True
        review0 = {"state": "CHANGES_REQUESTED", "commit_id": "1234"}
        review1 = {"state": "APPROVED", "commit_id": "1234"}
        review2 = {"state": "OTHER", "commit_id": "1234"}
        pr_response = utils.Response(json_data=pr_data)
        review_response = utils.Response(json_data=[review0, review1, review2])
        mock_get.side_effect = [pr_response, review_response]
        mock_get.call_count = 0
        mock_put.call_count = 0
        with self.settings(INSTALLED_GITSERVERS=[
            utils.github_config(remote_update=True, repo_settings=repo_settings)]):

            api = self.server.api()
            # Changes requested
            self.assertFalse(api.automerge(repo, 1))
            self.assertEqual(mock_put.call_count, 0)

            # Not approved
            review_response = utils.Response(json_data=[review2])
            mock_get.side_effect = [pr_response, review_response]
            self.assertFalse(api.automerge(repo, 1))
            self.assertEqual(mock_put.call_count, 0)

            # No reviews
            review_response = utils.Response(json_data=[])
            mock_get.side_effect = [pr_response, review_response]
            self.assertFalse(api.automerge(repo, 1))
            self.assertEqual(mock_put.call_count, 0)

            # Approved, should get merged
            review_response = utils.Response(json_data=[review1, review2])
            mock_get.side_effect = [pr_response, review_response]
            self.assertTrue(api.automerge(repo, 1))
            self.assertEqual(mock_put.call_count, 1)

