
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

class Tests(TestCase):
    fixtures = ['base.json',]

    def setUp(self):
        self.client = Client()
        self.factory = RequestFactory()
        self.server = models.GitServer.objects.filter(host_type=settings.GITSERVER_BITBUCKET).first()
        self.user = utils.create_user_with_token(server=self.server)
        utils.simulate_login(self.client.session, self.user)
        self.auth = self.user.server.auth().start_session_for_user(self.user)
        self.gapi = api.BitBucketAPI()

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
        mock_get.return_value = utils.Response(json_data={'message': 'message'})
        repos = self.gapi.get_repos(self.auth, self.client.session)
        # shouldn't be any repos
        self.assertEqual(len(repos), 0)

        mock_get.return_value = utils.Response(json_data=[{'owner': self.user.name, 'name': 'repo1'}, {'owner': self.user.name, 'name': 'repo2'}])
        repos = self.gapi.get_repos(self.auth, self.client.session)
        self.assertEqual(len(repos), 2)

        session = self.client.session
        session['bitbucket_repos'] = ['newrepo1']
        session['bitbucket_org_repos'] = ['org/repo1']
        session.save()
        repos = self.gapi.get_repos(self.auth, self.client.session)
        self.assertEqual(len(repos), 1)
        self.assertEqual(repos[0], 'newrepo1')

    @patch.object(OAuth2Session, 'get')
    def test_get_org_repos(self, mock_get):
        mock_get.return_value = utils.Response(json_data={'message': 'message'})
        repos = self.gapi.get_org_repos(self.auth, self.client.session)
        # shouldn't be any repos
        self.assertEqual(len(repos), 0)

        mock_get.return_value = utils.Response(json_data=[{'owner': 'org', 'name': 'repo1'}, {'owner': 'org', 'name': 'repo2'}])
        repos = self.gapi.get_org_repos(self.auth, self.client.session)
        self.assertEqual(len(repos), 2)

        session = self.client.session
        session['bitbucket_repos'] = ['newrepo1']
        session['bitbucket_org_repos'] = ['org/newrepo1']
        session.save()
        repos = self.gapi.get_org_repos(self.auth, self.client.session)
        self.assertEqual(len(repos), 1)
        self.assertEqual(repos[0], 'org/newrepo1')

    @patch.object(OAuth2Session, 'get')
    def test_get_all_repos(self, mock_get):
        mock_get.return_value = utils.Response(json_data={'message': 'message'})
        repos = self.gapi.get_all_repos(self.auth, self.user.name)
        # shouldn't be any repos
        self.assertEqual(len(repos), 0)

        mock_get.return_value = utils.Response(json_data=[
          {'owner': self.user.name, 'name': 'repo1'},
          {'owner': self.user.name, 'name': 'repo2'},
          {'owner': "other", 'name': 'repo1'},
          {'owner': "other", 'name': 'repo2'},
          ])
        repos = self.gapi.get_all_repos(self.auth, self.user.name)
        self.assertEqual(len(repos), 4)

    @patch.object(OAuth2Session, 'get')
    def test_get_branches(self, mock_get):
        repo = utils.create_repo(user=self.user)
        mock_get.return_value = utils.Response(json_data={})
        branches = self.gapi.get_branches(self.auth, self.user, repo)
        # shouldn't be any branch
        self.assertEqual(len(branches), 0)

        mock_get.return_value = utils.Response(json_data={'branch1': 'info', 'branch2': 'info'})
        branches = self.gapi.get_branches(self.auth, self.user, repo)
        self.assertEqual(len(branches), 2)

    def test_update_pr_status(self):
        self.gapi = api.BitBucketAPI()
        self.gapi.update_pr_status('session', 'base', 'head', 'state', 'event_url', 'description', 'context')

    @patch.object(OAuth2Session, 'get')
    def test_is_collaborator(self, mock_get):
        repo = utils.create_repo(user=self.user)
        # user is repo owner
        self.assertTrue(self.gapi.is_collaborator(self.auth, self.user, repo))
        user2 = utils.create_user('user2', server=self.server)
        repo = utils.create_repo(user=user2)
        # a collaborator
        mock_get.return_value = utils.Response(json_data={'values': [{'name': repo.name}]}, status_code=200)
        self.assertTrue(self.gapi.is_collaborator(self.auth, self.user, repo))
        # not a collaborator
        mock_get.return_value = utils.Response(status_code=404)
        self.assertFalse(self.gapi.is_collaborator(self.auth, self.user, repo))

    @patch.object(OAuth2Session, 'get')
    def test_last_sha(self, mock_get):
        branch = utils.create_branch(user=self.user)
        mock_get.return_value = utils.Response(json_data={branch.name: {'raw_node': '123'}})
        sha = self.gapi.last_sha(self.auth, self.user.name, branch.repository.name, branch.name)
        self.assertEqual(sha, '123')

        mock_get.return_value = utils.Response({})
        sha = self.gapi.last_sha(self.auth, self.user.name, branch.repository.name, branch.name)
        self.assertEqual(sha, None)

        mock_get.side_effect = Exception()
        sha = self.gapi.last_sha(self.auth, self.user.name, branch.repository.name, branch.name)
        self.assertEqual(sha, None)

    @patch.object(OAuth2Session, 'get')
    def test_get_all_pages(self, mock_get):
        init_response = utils.Response(json_data=[{'foo': 'bar'}], use_links=True)
        mock_get.return_value = utils.Response(json_data=[{'bar': 'foo'}], use_links=False)
        all_json = self.gapi.get_all_pages(self.auth, init_response)
        self.assertEqual(len(all_json), 2)
        self.assertIn('foo', all_json[0])
        self.assertIn('bar', all_json[1])

    @patch.object(OAuth2Session, 'get')
    @patch.object(OAuth2Session, 'post')
    def test_install_webhooks(self, mock_post, mock_get):
        repo = utils.create_repo(user=self.user)
        get_data ={'values': [{'events': ['pullrequest:created', 'repo:push'], 'url': 'no_url'}]}
        request = self.factory.get('/')
        callback_url = request.build_absolute_uri(reverse('ci:bitbucket:webhook', args=[self.user.build_key]))

        mock_get.return_value = utils.Response(json_data=get_data)
        mock_post.return_value = utils.Response(json_data={}, status_code=404)
        settings.INSTALL_WEBHOOK = True
        # with this data it should try to install the hook but there is an error
        with self.assertRaises(GitException):
            self.gapi.install_webhooks(request, self.auth, self.user, repo)

        # with this data it should do the hook
        mock_post.return_value = utils.Response(json_data={}, status_code=201)
        self.gapi.install_webhooks(request, self.auth, self.user, repo)

        # with this data the hook already exists
        get_data['values'][0]['url'] = callback_url
        self.gapi.install_webhooks(request, self.auth, self.user, repo)

        settings.INSTALL_WEBHOOK = False
        # this should just return
        self.gapi.install_webhooks(request, self.auth, self.user, repo)

    @patch.object(OAuth2Session, 'post')
    def test_pr_comment(self, mock_post):
        # no real state that we can check, so just go for coverage
        settings.REMOTE_UPDATE = True
        mock_post.return_value = utils.Response(status_code=200)
        # valid post
        self.gapi.pr_comment(self.auth, 'url', 'message')

        # bad post
        mock_post.return_value = utils.Response(status_code=400, json_data={'message': 'bad post'})
        self.gapi.pr_comment(self.auth, 'url', 'message')

        # bad post
        mock_post.side_effect = Exception()
        self.gapi.pr_comment(self.auth, 'url', 'message')

        settings.REMOTE_UPDATE = False
        # should just return
        self.gapi.pr_comment(self.auth, 'url', 'message')

    def test_basic_coverage(self):
        self.assertEqual(self.gapi.sign_in_url(), reverse('ci:bitbucket:sign_in'))
        self.gapi.user_url()
        self.gapi.repos_url()
        self.gapi.repo_url("owner", "repo")
        self.gapi.branches_url("owner", "repo")
        self.gapi.repo_html_url("owner", "repo")
        self.gapi.pr_html_url("owner", "repo", 1)
        self.gapi.branch_html_url("owner", "repo", "branch")
        self.gapi.git_url("owner", "repo")
        self.gapi.commit_html_url("owner", "repo", "1234")
        self.gapi.pr_comment_api_url("owner", "repo", 1)
        self.gapi.commit_comment_url("owner", "repo", "1234")
        self.gapi.collaborator_url("owner")

    def test_unimplemented(self):
        """
        Just get coverage on the warning messages for the unimplementd functions
        """
        self.gapi.add_pr_label(None, None, None, None)
        self.gapi.remove_pr_label(None, None, None, None)
        self.gapi.get_pr_comments(None, None, None, None)
        self.gapi.remove_pr_comment(None, None)
        self.gapi.edit_pr_comment(None, None, None)
