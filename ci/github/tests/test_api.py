
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
from django.test import override_settings
from requests_oauthlib import OAuth2Session
from ci.tests import utils as test_utils
from ci.github import api
from ci.git_api import GitException
from mock import patch
import os, json
from ci.tests import DBTester

@override_settings(INSTALLED_GITSERVERS=[test_utils.github_config()])
class Tests(DBTester.DBTester):
    def setUp(self):
        super(Tests, self).setUp()
        self.create_default_recipes()
        test_utils.simulate_login(self.client.session, self.build_user)
        self.auth = self.build_user.server.auth().start_session_for_user(self.build_user)

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
        self.compare_counts(num_git_events=1)

        # now there are recipes so jobs should get created
        py_data = json.loads(t1)
        py_data['pull_request']['base']['repo']['owner']['login'] = self.owner.name
        py_data['pull_request']['base']['repo']['name'] = self.repo.name

        self.set_counts()
        response = self.client.post(url, data=json.dumps(py_data), content_type="application/json")
        self.assertEqual(response.content, "OK")
        self.compare_counts(jobs=2, events=1, ready=1, users=1, repos=1, branches=1, commits=2, prs=1, active=2, active_repos=1, num_git_events=1)

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
        self.compare_counts(num_git_events=1)

        py_data = json.loads(t1)
        py_data['repository']['owner']['name'] = self.owner.name
        py_data['repository']['name'] = self.repo.name
        py_data['ref'] = 'refs/heads/{}'.format(self.branch.name)

        # now there are recipes so jobs should get created
        self.set_counts()
        response = self.client.post(url, data=json.dumps(py_data), content_type="application/json")
        self.assertEqual(response.content, "OK")
        self.compare_counts(jobs=2, ready=1, events=1, commits=2, active=2, active_repos=1, num_git_events=1)

    def test_status_str(self):
        api = self.server.api()
        self.assertEqual(api.status_str(api.SUCCESS), 'success')
        self.assertEqual(api.status_str(1000), None)

    @patch.object(api.GitHubAPI, 'get_all_pages')
    @patch.object(OAuth2Session, 'get')
    def test_get_repos(self, mock_get, mock_get_all_pages):
        mock_get_all_pages.return_value = {'message': 'message'}
        mock_get.return_value = test_utils.Response(status_code=200)
        api = self.server.api()
        repos = api.get_repos(self.auth, self.client.session)
        # shouldn't be any repos
        self.assertEqual(len(repos), 0)

        mock_get_all_pages.return_value = [{'name': 'repo1', 'owner': {'login': 'owner'} }, {'name': 'repo2', 'owner': {'login': 'owner'}}]
        repos = api.get_repos(self.auth, self.client.session)
        self.assertEqual(len(repos), 2)

        session = self.client.session
        session[api._repos_key] = ['owner/repo1']
        session.save()
        repos = api.get_repos(self.auth, self.client.session)
        self.assertEqual(len(repos), 1)
        self.assertEqual(repos[0], 'owner/repo1')

    @patch.object(api.GitHubAPI, 'get_all_pages')
    @patch.object(OAuth2Session, 'get')
    def test_get_org_repos(self, mock_get, mock_get_all_pages):
        mock_get_all_pages.return_value = {'message': 'message'}
        mock_get.return_value = test_utils.Response(status_code=200)
        api = self.server.api()
        repos = api.get_org_repos(self.auth, self.client.session)
        # shouldn't be any repos
        self.assertEqual(len(repos), 0)

        mock_get_all_pages.return_value = [{'name': 'repo1', 'owner':{'login':'owner'}}, {'name': 'repo2', 'owner':{'login':'owner'}}]
        repos = api.get_org_repos(self.auth, self.client.session)
        self.assertEqual(len(repos), 2)

        session = self.client.session
        session[api._org_repos_key] = ['newrepo1']
        session.save()
        repos = api.get_org_repos(self.auth, self.client.session)
        self.assertEqual(len(repos), 1)
        self.assertEqual(repos[0], 'newrepo1')

    @patch.object(api.GitHubAPI, 'get_all_pages')
    @patch.object(OAuth2Session, 'get')
    def test_get_all_repos(self, mock_get, mock_get_all_pages):
        mock_get_all_pages.return_value = {'message': 'message'}
        mock_get.return_value = test_utils.Response(status_code=200)
        api = self.server.api()
        repos = api.get_all_repos(self.auth, self.build_user.name)
        # shouldn't be any repos
        self.assertEqual(len(repos), 0)

        mock_get_all_pages.return_value = [{'name': 'repo1', 'owner':{'login':'owner'}}, {'name': 'repo2', 'owner':{'login':'owner'}}]
        repos = api.get_all_repos(self.auth, self.build_user.name)
        self.assertEqual(len(repos), 4)

    @patch.object(api.GitHubAPI, 'get_all_pages')
    @patch.object(OAuth2Session, 'get')
    def test_get_branches(self, mock_get, mock_get_all_pages):
        mock_get_all_pages.return_value = {'message': 'message'}
        mock_get.return_value = test_utils.Response(status_code=200)
        api = self.server.api()
        branches = api.get_branches(self.auth, self.owner, self.repo)
        # shouldn't be any branch
        self.assertEqual(len(branches), 0)

        mock_get_all_pages.return_value = [{'name': 'branch1'}, {'name': 'branch2'}]
        branches = api.get_branches(self.auth, self.owner, self.repo)
        self.assertEqual(len(branches), 2)

    @patch.object(OAuth2Session, 'post')
    def test_update_pr_status(self, mock_post):
        ev = test_utils.create_event(user=self.build_user)
        pr = test_utils.create_pr()
        ev.pull_request = pr
        ev.save()
        # no state is set so just run for coverage
        with self.settings(INSTALLED_GITSERVERS=[test_utils.github_config(remote_update=True)]):
            mock_post.return_value = test_utils.Response(content='updated_at')
            api = self.server.api()
            api.update_pr_status(self.auth, ev.base, ev.head, api.PENDING, 'event', 'desc', 'context', api.STATUS_JOB_STARTED)
            self.assertEqual(mock_post.call_count, 1)

            mock_post.return_value = test_utils.Response(content='nothing')
            api.update_pr_status(self.auth, ev.base, ev.head, api.PENDING, 'event', 'desc', 'context', api.STATUS_JOB_STARTED)
            self.assertEqual(mock_post.call_count, 2)

            mock_post.side_effect = Exception('exception')
            api.update_pr_status(self.auth, ev.base, ev.head, api.PENDING, 'event', 'desc', 'context', api.STATUS_JOB_STARTED)
            self.assertEqual(mock_post.call_count, 3)

        # This should just return
        api = self.server.api()
        api.update_pr_status(self.auth, ev.base, ev.head, api.PENDING, 'event', 'desc', 'context', api.STATUS_JOB_STARTED)
        self.assertEqual(mock_post.call_count, 3)

    @patch.object(OAuth2Session, 'get')
    def test_is_collaborator(self, mock_get):
        # user is repo owner
        api = self.server.api()
        self.assertTrue(api.is_collaborator(self.auth, self.owner, self.repo))
        user2 = test_utils.create_user('user2')
        repo = test_utils.create_repo(user=user2)
        # a collaborator
        mock_get.return_value = test_utils.Response(status_code=204)
        self.assertTrue(api.is_collaborator(self.auth, self.build_user, repo))
        # not a collaborator
        mock_get.return_value = test_utils.Response(status_code=404)
        self.assertFalse(api.is_collaborator(self.auth, self.build_user, repo))
        #doesn't have permission to check collaborator
        mock_get.return_value = test_utils.Response(status_code=403)
        self.assertFalse(api.is_collaborator(self.auth, self.build_user, repo))
        #some other response code
        mock_get.return_value = test_utils.Response(status_code=405)
        self.assertFalse(api.is_collaborator(self.auth, self.build_user, repo))

    class ShaResponse(test_utils.Response):
        def __init__(self, commit=True, *args, **kwargs):
            test_utils.Response.__init__(self, *args, **kwargs)
            if commit:
                self.content = '{\n\t"commit": {\n\t\t"sha": "123"\n\t}\n}'
            else:
                self.content = 'nothing'

    @patch.object(OAuth2Session, 'get')
    def test_last_sha(self, mock_get):
        mock_get.return_value = self.ShaResponse(True)
        api = self.server.api()
        sha = api.last_sha(self.auth, self.build_user.name, self.branch.repository.name, self.branch.name)
        self.assertEqual(sha, '123')

        mock_get.return_value = self.ShaResponse(False)
        sha = api.last_sha(self.auth, self.build_user, self.branch.repository.name, self.branch.name)
        self.assertEqual(sha, None)

        mock_get.side_effect = Exception()
        sha = api.last_sha(self.auth, self.build_user, self.branch.repository.name, self.branch.name)
        self.assertEqual(sha, None)

    @patch.object(OAuth2Session, 'get')
    def test_tag_sha(self, mock_get):
        jdata = [{"name": "tagname",
                "commit": {"sha": "123"},
                }]
        mock_get.return_value = test_utils.Response(jdata)
        api = self.server.api()
        sha = api.tag_sha(self.auth, self.build_user.name, self.branch.repository.name, "tagname")
        self.assertEqual(sha, '123')

        jdata[0]["name"] = "othertag"
        mock_get.return_value = test_utils.Response(jdata)
        sha = api.tag_sha(self.auth, self.build_user, self.branch.repository.name, "tagname")
        self.assertEqual(sha, None)

        mock_get.side_effect = Exception()
        sha = api.tag_sha(self.auth, self.build_user, self.branch.repository.name, "tagname")
        self.assertEqual(sha, None)

    @patch.object(OAuth2Session, 'get')
    def test_get_all_pages(self, mock_get):
        init_response = test_utils.Response([{'foo': 'bar'}], use_links=True)
        mock_get.return_value = test_utils.Response([{'bar': 'foo'}])
        api = self.server.api()
        all_json = api.get_all_pages(self.auth, init_response)
        self.assertEqual(len(all_json), 2)
        self.assertIn('foo', all_json[0])
        self.assertIn('bar', all_json[1])

    @patch.object(OAuth2Session, 'get')
    @patch.object(OAuth2Session, 'post')
    @override_settings(INSTALLED_GITSERVERS=[test_utils.github_config(install_webhook=True)])
    def test_install_webhooks(self, mock_post, mock_get):
        get_data = []
        base = self.server.server_config().get("civet_base_url", "")
        callback_url = "%s%s" % (base, reverse('ci:github:webhook', args=[self.build_user.build_key]))
        get_data.append({'events': ['push'], 'config': {'url': 'no_url', 'content_type': 'json'}})
        get_data.append({'events': ['pull_request'], 'config': {'url': 'no_url', 'content_type': 'json'}})
        mock_get.return_value = test_utils.Response(get_data, status_code=400)
        mock_post.return_value = test_utils.Response({'errors': 'error'})

        # can't even get the webhooks
        api = self.server.api()
        with self.assertRaises(GitException):
            api.install_webhooks(self.auth, self.build_user, self.repo)

        # got the webhooks, none are valid, error trying to install
        get_data.append({'events': [], 'config': {'url': 'no_url', 'content_type': 'json'}})
        mock_get.return_value = test_utils.Response(get_data)
        with self.assertRaises(GitException):
            api.install_webhooks(self.auth, self.build_user, self.repo)

        mock_post.return_value = test_utils.Response({'errors': 'error'}, status_code=404)
        with self.assertRaises(GitException):
            api.install_webhooks(self.auth, self.build_user, self.repo)

        # with this data it should do the hook
        get_data.append({'events': ['pull_request', 'push'], 'config': {'url': 'no_url', 'content_type': 'json'}})
        mock_post.return_value = test_utils.Response({})
        api.install_webhooks(self.auth, self.build_user, self.repo)

        # with this data the hook already exists
        get_data.append({'events': ['pull_request', 'push'], 'config': {'url': callback_url, 'content_type': 'json'}})
        api.install_webhooks(self.auth, self.build_user, self.repo)

        with self.settings(INSTALLED_GITSERVERS=[test_utils.github_config(install_webhook=False)]):
            # this should just return
            count = mock_get.call_count
            self.server.api().install_webhooks(self.auth, self.build_user, self.repo)
            self.assertEqual(mock_get.call_count, count)

    @patch.object(OAuth2Session, 'get')
    @patch.object(OAuth2Session, 'delete')
    def test_remove_pr_todo_labels(self, mock_del, mock_get):
        # We can't really test this very well, so just try to get some coverage
        # The title has the remove prefix so it would get deleted
        prefix = self.server.server_config()["remove_pr_label_prefix"][0]
        data = [{"name": "%s Address Comments" % prefix}, {"name": "Other"}]
        mock_get.return_value = test_utils.Response(data)
        mock_del.return_value = test_utils.Response({})
        with self.settings(INSTALLED_GITSERVERS=[test_utils.github_config(remote_update=True)]):
            api = self.server.api()
            api.remove_pr_todo_labels(self.build_user, self.build_user.name, self.repo.name, 1)
            self.assertEqual(mock_get.call_count, 1)
            self.assertEqual(mock_del.call_count, 1)

            # The title has the remove prefix but the request raised an exception
            mock_del.return_value = test_utils.Response({}, do_raise=True)
            mock_get.call_count = 0
            mock_del.call_count = 0
            api.remove_pr_todo_labels(self.build_user, self.build_user.name, self.repo.name, 1)
            self.assertEqual(mock_get.call_count, 1)
            self.assertEqual(mock_del.call_count, 1)

            # The title doesn't have the remove prefix
            mock_get.return_value = test_utils.Response([{"name": "NOT A PREFIX Address Comments"}, {"name": "Other"}])
            mock_del.return_value = test_utils.Response({})
            mock_get.call_count = 0
            mock_del.call_count = 0
            api.remove_pr_todo_labels(self.build_user, self.build_user.name, self.repo.name, 1)
            self.assertEqual(mock_get.call_count, 1)
            self.assertEqual(mock_del.call_count, 0)

        # We aren't updating the server
        mock_get.call_count = 0
        mock_del.call_count = 0
        self.server.api().remove_pr_todo_labels(self.build_user, self.build_user.name, self.repo.name, 1)
        self.assertEqual(mock_get.call_count, 0)
        self.assertEqual(mock_del.call_count, 0)

    def test_basic_coverage(self):
        api = self.server.api()
        api.sign_in_url()
        api.repos_url("owner")
        api.git_url("owner", "repo")
        api.repo_url("owner", "repo")
        api.status_url("owner", "repo", "sha")
        api.branches_url("owner", "repo")
        api.branch_html_url("owner", "repo", "branch")
        api.branch_url("owner", "repo", "branch")
        api.repo_html_url("owner", "repo")
        api.commit_comment_url("owner", "repo", "sha")
        api.commit_url("owner", "repo", "sha")
        api.commit_html_url("owner", "repo", "sha")
        api.collaborator_url("owner", "repo", "user")
        api.pr_labels_url("owner", "repo", 1)
        api.pr_html_url("owner", "repo", 1)

    @patch.object(OAuth2Session, 'post')
    def test_post_data(self, mock_post):
        url = "Some URL"
        data = {"key0": "value0", "key1": "value1"}
        response_data = {"return": "value"}
        mock_post.return_value = test_utils.Response(response_data)
        # By default REMOTE_UPDATE=False so this shouldn't return anything
        self.assertEqual(self.server.api()._post_data(self.auth, url, data), None)

        with self.settings(INSTALLED_GITSERVERS=[test_utils.github_config(remote_update=True)]):
            # Everything OK, so should return our response data
            api = self.server.api()
            self.assertEqual(api._post_data(self.auth, url, data), response_data)
            mock_post.return_value = test_utils.Response(response_data, do_raise=True)

            # An exception occured, should return None
            self.assertEqual(api._post_data(self.auth, url, data), None)

            mock_post.return_value = test_utils.Response(response_data)
            msg = "Message"
            self.assertEqual(api.pr_comment(self.auth, url, msg), None)
            sha = "1234"
            path = "filepath"
            position = 1
            self.assertEqual(api.pr_review_comment(self.auth, url, sha, path, position, msg), None)

    @patch.object(api.GitHubAPI, 'get_all_pages')
    @patch.object(OAuth2Session, 'get')
    @override_settings(INSTALLED_GITSERVERS=[test_utils.github_config(remote_update=True)])
    def test_get_pr_changed_files(self, mock_get, mock_get_all_pages):
        api = self.server.api()
        pr = test_utils.create_pr(repo=self.repo)
        mock_get_all_pages.return_value = {'message': 'message'}
        mock_get.return_value = test_utils.Response(status_code=200)
        files = api.get_pr_changed_files(self.build_user, self.repo.user.name, self.repo.name, pr.number)
        # shouldn't be any files
        self.assertEqual(len(files), 0)

        file_json = self.get_json_file("files.json")
        file_data = json.loads(file_json)
        mock_get_all_pages.return_value = file_data
        files = api.get_pr_changed_files(self.build_user, self.repo.user.name, self.repo.name, pr.number)
        self.assertEqual(len(files), 2)
        self.assertEqual(["other/path/to/file1", "path/to/file0"], files)

        # simulate a bad request
        mock_get.return_value = test_utils.Response(status_code=400)
        files = api.get_pr_changed_files(self.build_user, self.repo.user.name, self.repo.name, pr.number)
        self.assertEqual(files, [])

        # simulate a request timeout
        mock_get.side_effect = Exception("Bam!")
        files = api.get_pr_changed_files(self.build_user, self.repo.user.name, self.repo.name, pr.number)
        self.assertEqual(files, [])

    @patch.object(OAuth2Session, 'post')
    def test_add_pr_label(self, mock_post):
        # should just return
        self.server.api().add_pr_label(None, None, None, None)
        self.assertEqual(mock_post.call_count, 0)

        with self.settings(INSTALLED_GITSERVERS=[test_utils.github_config(remote_update=True)]):
            pr = test_utils.create_pr(repo=self.repo)
            mock_post.return_value = test_utils.Response(status_code=200)

            api = self.server.api()
            # No label, no problem
            api.add_pr_label(self.build_user, self.repo, pr.number, None)
            self.assertEqual(mock_post.call_count, 0)

            # valid label
            api.add_pr_label(self.build_user, self.repo, pr.number, 'foo')
            self.assertEqual(mock_post.call_count, 1)

            # bad response
            mock_post.return_value = test_utils.Response(status_code=400)
            api.add_pr_label(self.build_user, self.repo, pr.number, 'foo')
            self.assertEqual(mock_post.call_count, 2)

    @patch.object(OAuth2Session, 'delete')
    def test_remove_pr_label(self, mock_delete):
        # should just return
        self.server.api().remove_pr_label(None, None, None, None)
        self.assertEqual(mock_delete.call_count, 0)

        with self.settings(INSTALLED_GITSERVERS=[test_utils.github_config(remote_update=True)]):
            pr = test_utils.create_pr(repo=self.repo)
            mock_delete.return_value = test_utils.Response(status_code=200)
            api = self.server.api()

            # No label, no problem
            api.remove_pr_label(self.build_user, self.repo, pr.number, None)
            self.assertEqual(mock_delete.call_count, 0)

            # valid label
            api.remove_pr_label(self.build_user, self.repo, pr.number, 'foo')
            self.assertEqual(mock_delete.call_count, 1)

            # bad response
            mock_delete.return_value = test_utils.Response(status_code=400)
            api.remove_pr_label(self.build_user, self.repo, pr.number, 'foo bar')
            self.assertEqual(mock_delete.call_count, 2)

            # 404, label probably isn't there
            mock_delete.return_value = test_utils.Response(status_code=404)
            api.remove_pr_label(self.build_user, self.repo, pr.number, 'foo')
            self.assertEqual(mock_delete.call_count, 3)

    @patch.object(OAuth2Session, 'get')
    def test_get_pr_comments(self, mock_get):
        # should just return
        ret = self.server.api().get_pr_comments(None, None, None, None)
        self.assertEqual(mock_get.call_count, 0)
        self.assertEqual(ret, [])

        with self.settings(INSTALLED_GITSERVERS=[test_utils.github_config(remote_update=True)]):
            # bad response, should return empty list
            mock_get.return_value = test_utils.Response(status_code=400)
            comment_re = r"^some message"
            api = self.server.api()
            ret = api.get_pr_comments(self.auth, "some_url", self.build_user.name, comment_re)
            self.assertEqual(mock_get.call_count, 1)
            self.assertEqual(ret, [])

            c0 = {"user": {"login": self.build_user.name}, "body": "some message"}
            c1 = {"user": {"login": self.build_user.name}, "body": "other message"}
            c2 = {"user": {"login": "nobody"}, "body": "some message"}
            mock_get.return_value = test_utils.Response(json_data=[c0, c1, c2])

            ret = api.get_pr_comments(self.auth, "some_url", self.build_user.name, comment_re)
            self.assertEqual(ret, [c0])

    @patch.object(OAuth2Session, 'delete')
    def test_remove_pr_comment(self, mock_del):
        # should just return
        self.server.api().remove_pr_comment(None, None)
        self.assertEqual(mock_del.call_count, 0)

        with self.settings(INSTALLED_GITSERVERS=[test_utils.github_config(remote_update=True)]):
            comment = {"url": "some_url"}
            # bad response
            api = self.server.api()
            mock_del.return_value = test_utils.Response(status_code=400)
            api.remove_pr_comment(self.auth, comment)
            self.assertEqual(mock_del.call_count, 1)

            # good response
            mock_del.return_value = test_utils.Response()
            api.remove_pr_comment(self.auth, comment)
            self.assertEqual(mock_del.call_count, 2)

    @patch.object(OAuth2Session, 'patch')
    def test_edit_pr_comment(self, mock_edit):
        # should just return
        self.server.api().edit_pr_comment(None, None, None)
        self.assertEqual(mock_edit.call_count, 0)

        with self.settings(INSTALLED_GITSERVERS=[test_utils.github_config(remote_update=True)]):
            comment = {"url": "some_url"}
            api = self.server.api()
            # bad response
            mock_edit.return_value = test_utils.Response(status_code=400)
            api.edit_pr_comment(self.auth, comment, "new msg")
            self.assertEqual(mock_edit.call_count, 1)

            # good response
            mock_edit.return_value = test_utils.Response()
            api.edit_pr_comment(self.auth, comment, "new msg")
            self.assertEqual(mock_edit.call_count, 2)

    @patch.object(OAuth2Session, 'get')
    def test_is_team_member(self, mock_get):
        team_data = {"state": "active"}
        api = self.server.api()
        mock_get.return_value = test_utils.Response(team_data, status_code=404)
        # Not a member
        is_member = api._is_team_member(self.auth, 100, "username")
        self.assertFalse(is_member)

        # Is an active member
        mock_get.return_value = test_utils.Response(team_data)
        is_member = api._is_team_member(self.auth, 100, "username")
        self.assertTrue(is_member)

        # Is a pending member
        team_data = {"state": "pending"}
        mock_get.return_value = test_utils.Response(team_data)
        is_member = api._is_team_member(self.auth, 100, "username")
        self.assertFalse(is_member)

        mock_get.side_effect = Exception("Bam!")
        # Bad request
        is_member = api._is_team_member(self.auth, 100, "username")
        self.assertFalse(is_member)

    @patch.object(OAuth2Session, 'get')
    def test_is_org_member(self, mock_get):
        org_data = {"login": "org"}
        mock_get.return_value = test_utils.Response([org_data], status_code=404)
        api = self.server.api()
        # Bad response
        is_member = api._is_org_member(self.auth, "org")
        self.assertFalse(is_member)

        # Is a member
        mock_get.return_value = test_utils.Response([org_data])
        is_member = api._is_org_member(self.auth, "org")
        self.assertTrue(is_member)

        # Is not a member
        is_member = api._is_org_member(self.auth, "other_org")
        self.assertFalse(is_member)

        mock_get.side_effect = Exception("Bam!")
        # Bad request
        is_member = api._is_org_member(self.auth, "org")
        self.assertFalse(is_member)

    @patch.object(OAuth2Session, 'get')
    def test_get_team_id(self, mock_get):
        team_data = {"name": "foo", "id": "100"}
        response = test_utils.Response([team_data])
        mock_get.return_value = response
        api = self.server.api()
        # No matching team id
        team_id = api.get_team_id(self.auth, "bar", "bar")
        self.assertIsNone(team_id)

        # Matching team id
        team_id = api.get_team_id(self.auth, "bar", "foo")
        self.assertEqual(team_id, "100")

        mock_get.side_effect = Exception("Bam!")
        # Bad call
        team_id = api.get_team_id(self.auth, "bar", "foo")
        self.assertIsNone(team_id)

    @patch.object(OAuth2Session, 'get')
    def test_is_member(self, mock_get):
        user = test_utils.create_user()
        api = self.server.api()
        # Invalid team name
        is_member = api.is_member(self.auth, "bad/team/name", user)
        self.assertFalse(is_member)

        # Just a name so interpret as an organization or a user
        org_data = {"login": "org"}
        mock_get.return_value = test_utils.Response([org_data])
        is_member = api.is_member(self.auth, "org", user)
        self.assertTrue(is_member)

        # Just the user name
        is_member = api.is_member(self.auth, user.name, user)
        self.assertTrue(is_member)

        # No match
        is_member = api.is_member(self.auth, "other_org", user)
        self.assertFalse(is_member)

        # Try out the team name route
        team_id_data = {"name": "foo", "id": "100"}
        team_data = {"state": "active"}

        team_id_response = test_utils.Response([team_id_data])
        team_data_response = test_utils.Response(team_data)
        mock_get.side_effect = [team_id_response, team_data_response]

        # Correct team
        is_member = api.is_member(self.auth, "bar/foo", user)
        self.assertTrue(is_member)

        # Bad team
        mock_get.side_effect = [team_id_response, team_data_response]
        is_member = api.is_member(self.auth, "bar/foo foo", user)
        self.assertFalse(is_member)

    @patch.object(OAuth2Session, 'get')
    def test_get_open_prs(self, mock_get):
        repo = test_utils.create_repo()
        pr0 = {"title": "some title", "number": 123, "html_url": "some url"}
        mock_get.return_value = test_utils.Response([pr0])
        prs = self.gapi.get_open_prs(self.auth, repo.user.name, repo.name)
        self.assertEquals([pr0], prs)

        mock_get.side_effect = Exception("BAM!")
        prs = self.gapi.get_open_prs(self.auth, repo.user.name, repo.name)
        self.assertEquals(prs, None)
