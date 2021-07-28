
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
from django.conf import settings
from django.test import override_settings
from django.urls import reverse
from mock import patch
from ci import models
from ci.tests import utils
import os, json
from ci.gitlab import views
from ci.tests import DBTester
from requests_oauthlib import OAuth2Session

class PrResponse(utils.Response):
    def __init__(self, user, repo, commit='1', title='testTitle', *args, **kwargs):
        """
        All the responses all in one dict
        """
        data = {'title': title,
            'path_with_namespace': '{}/{}'.format(user.name, repo.name),
            'iid': '1',
            'owner': {'username': user.name},
            'name': repo.name,
            'commit': {'id': commit},
            'ssh_url_to_repo': 'testUrl',
            }
        super(PrResponse, self).__init__(json_data=data, *args, **kwargs)

class PushResponse(utils.Response):
    def __init__(self, user, repo, *args, **kwargs):
        data = {
            'name': repo.name,
            'namespace': {'name': user.name},
            'path_with_namespace' : '%s/%s' % (user.name, repo.name),
            }
        super(PushResponse, self).__init__(data, *args, **kwargs)


@override_settings(INSTALLED_GITSERVERS=[utils.gitlab_config()])
class Tests(DBTester.DBTester):
    def setUp(self):
        super(Tests, self).setUp()
        self.create_default_recipes(server_type=settings.GITSERVER_GITLAB)

    def get_data(self, fname):
        p = '{}/{}'.format(os.path.dirname(__file__), fname)
        with open(p, 'r') as f:
            contents = f.read()
            return contents

    def client_post_json(self, url, data):
        json_data = json.dumps(data)
        return self.client.post(url, json_data, content_type='application/json')

    def test_webhook(self):
        url = reverse('ci:gitlab:webhook', args=[10000])
        # only post allowed
        response = self.client.get(url)
        self.assertEqual(response.status_code, 405) # not allowed

        # no user
        data = {'key': 'value'}
        response = self.client_post_json(url, data)
        self.assertEqual(response.status_code, 400)

        # not json
        user = utils.get_test_user(server=self.server)
        url = reverse('ci:gitlab:webhook', args=[user.build_key])
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 400)

        # user with no recipes
        response = self.client_post_json(url, data)
        self.assertEqual(response.status_code, 400)

        # unknown json
        utils.create_recipe(user=user)
        response = self.client_post_json(url, data)
        self.assertEqual(response.status_code, 400)

    def test_close_pr(self):
        user = utils.get_test_user(server=self.server)
        repo = utils.create_repo(user=user)
        pr = utils.create_pr(repo=repo, number=1)
        pr.closed = False
        pr.save()
        views.close_pr('foo', 'bar', 1, user.server)
        pr.refresh_from_db()
        self.assertFalse(pr.closed)

        views.close_pr(user.name, 'bar', 1, user.server)
        pr.refresh_from_db()
        self.assertFalse(pr.closed)

        views.close_pr(user.name, repo.name, 0, user.server)
        pr.refresh_from_db()
        self.assertFalse(pr.closed)

        views.close_pr(user.name, repo.name, 1, user.server)
        pr.refresh_from_db()
        self.assertTrue(pr.closed)

    @patch.object(OAuth2Session, "get")
    def test_pull_request_bad_source(self, mock_get):
        """
        Sometimes the user hasn't given moosetest access to their repository
        and an error occurs. It is hard to check if a successful comment
        has happened but just try to get coverage.
        """
        data = self.get_data('pr_open_01.json')
        pr_data = json.loads(data)

        # Simulate an error on the server while getting the source branch
        mock_get.return_value = utils.Response(status_code=404)
        url = reverse('ci:gitlab:webhook', args=[self.build_user.build_key])

        self.set_counts()
        response = self.client_post_json(url, pr_data)
        self.assertEqual(response.status_code, 400)
        self.compare_counts()

    @patch.object(OAuth2Session, 'get')
    def test_pull_request(self, mock_get):
        """
        Unlike with GitHub, GitLab requires that you
        do a bunch of extra requests to get the needed information.
        Since we don't have authorization we have to mock these up.
        """
        data = self.get_data('pr_open_01.json')
        pr_data = json.loads(data)
        data = self.get_data('files.json')
        file_data = json.loads(data)
        data = self.get_data("user.json")
        user_data = json.loads(data)
        data = self.get_data("project_member.json")
        member_data = json.loads(data)

        # no recipe so no jobs so no event should be created
        pr_response = PrResponse(self.owner, self.repo)
        user_response = utils.Response(json_data=user_data)
        member_response = utils.Response(json_data=member_data)
        full_response = [pr_response, pr_response, user_response, member_response, utils.Response(json_data=file_data)]
        mock_get.side_effect = full_response
        url = reverse('ci:gitlab:webhook', args=[self.build_user.build_key])

        self.set_counts()
        response = self.client_post_json(url, pr_data)
        self.assertEqual(response.status_code, 200)
        self.compare_counts()

        pr_data['object_attributes']['target']['path_with_namespace'] = '%s/%s' % (self.owner.name, self.repo.name)
        pr_data['object_attributes']['target']['namespace'] = self.owner.name
        pr_data['object_attributes']['target']['name'] = self.repo.name

        # there is a recipe but the PR is a work in progress
        title = '[WIP] testTitle'
        pr_data['object_attributes']['title'] = title
        mock_get.return_value = PrResponse(self.owner, self.repo, title=title)
        mock_get.side_effect = None
        self.set_counts()
        response = self.client_post_json(url, pr_data)
        self.assertEqual(response.status_code, 200)
        self.compare_counts()

        # there is a recipe but the PR is a work in progress
        title = 'WIP: testTitle'
        pr_data['object_attributes']['title'] = title
        pr_response = PrResponse(self.owner, self.repo, title=title)
        full_response = [pr_response, pr_response, user_response, member_response, utils.Response(json_data=file_data)]
        mock_get.side_effect = full_response
        self.set_counts()
        response = self.client_post_json(url, pr_data)
        self.assertEqual(response.status_code, 200)
        self.compare_counts()

        # there is a recipe so a job should be made ready
        title = 'testTitle'
        pr_data['object_attributes']['title'] = title
        mock_get.side_effect = full_response
        self.set_counts()
        response = self.client_post_json(url, pr_data)
        self.assertEqual(response.status_code, 200)

        self.compare_counts(jobs=2,
                ready=1,
                events=1,
                users=1,
                repos=1,
                branches=2,
                commits=2,
                prs=1,
                active=2,
                active_repos=1,
                )
        ev = models.Event.objects.latest()
        self.assertEqual(ev.jobs.first().ready, True)
        self.assertEqual(ev.pull_request.title, 'testTitle')
        self.assertEqual(ev.pull_request.closed, False)
        self.assertEqual(ev.trigger_user, pr_data['user']['username'])

        # if it is the same commit nothing should happen
        self.set_counts()
        mock_get.side_effect = full_response
        response = self.client_post_json(url, pr_data)
        self.assertEqual(response.status_code, 200)
        self.compare_counts()

        # if the base commit changes but the head commit is
        # the same, nothing should happen
        target_response = PrResponse(self.owner, self.repo, commit='2')
        full_response[1] = target_response
        self.set_counts()
        mock_get.side_effect = full_response
        response = self.client_post_json(url, pr_data)
        self.assertEqual(response.status_code, 200)
        self.compare_counts()

        # if the head commit changes then new jobs should be created
        # and old ones canceled.
        source_response = PrResponse(self.owner, self.repo, commit='2')
        full_response[1] = pr_response
        full_response[0] = source_response
        self.set_counts()
        mock_get.side_effect = full_response
        response = self.client_post_json(url, pr_data)
        self.assertEqual(response.status_code, 200)
        self.compare_counts(jobs=2,
                ready=1,
                active=2,
                events=1,
                canceled=2,
                events_canceled=1,
                num_changelog=2,
                num_events_completed=1,
                num_jobs_completed=2,
                commits=1,
                )

        pr_data['object_attributes']['state'] = 'closed'
        self.set_counts()
        mock_get.side_effect = full_response
        response = self.client_post_json(url, pr_data)
        self.assertEqual(response.status_code, 200)
        self.compare_counts(pr_closed=True)

        pr_data['object_attributes']['state'] = 'reopened'
        self.set_counts()
        mock_get.side_effect = full_response
        response = self.client_post_json(url, pr_data)
        self.assertEqual(response.status_code, 200)
        self.compare_counts(pr_closed=False)

        pr_data['object_attributes']['state'] = 'synchronize'
        self.set_counts()
        mock_get.side_effect = full_response
        response = self.client_post_json(url, pr_data)
        self.assertEqual(response.status_code, 200)
        self.compare_counts()

        pr_data['object_attributes']['state'] = 'merged'
        self.set_counts()
        mock_get.side_effect = full_response
        response = self.client_post_json(url, pr_data)
        self.assertEqual(response.status_code, 200)
        self.compare_counts(pr_closed=True)

        pr_data['object_attributes']['state'] = 'unknown'
        self.set_counts()
        mock_get.side_effect = full_response
        response = self.client_post_json(url, pr_data)
        self.assertEqual(response.status_code, 400)
        self.compare_counts(pr_closed=True)

    @patch.object(OAuth2Session, "get")
    def test_push(self, mock_get):
        """
        The push event for GitLab just gives project ids and user ids
        which isn't enough information.
        It does an additional request to get more information about
        the project.
        """
        data = self.get_data('push_01.json')
        push_data = json.loads(data)

        # no recipe so no jobs should be created
        self.set_counts()
        mock_get.return_value = PushResponse(self.owner, self.repo)
        url = reverse('ci:gitlab:webhook', args=[self.build_user.build_key])
        response = self.client_post_json(url, push_data)
        self.assertEqual(response.status_code, 200)
        self.compare_counts()
        self.assertEqual(response.content, b"OK")

        push_data['ref'] = "refs/heads/%s" % self.branch.name

        self.set_counts()
        response = self.client_post_json(url, push_data)
        self.assertEqual(response.status_code, 200)
        self.compare_counts(jobs=2, ready=1, events=1, commits=2, active=2, active_repos=1)
        self.assertEqual(response.content, b"OK")

        push_data['commits'] = []

        self.set_counts()
        mock_get.call_count = 0
        response = self.client_post_json(url, push_data)
        self.assertEqual(response.status_code, 200)
        self.compare_counts()
        self.assertEqual(response.content, b"OK")
        self.assertEqual(mock_get.call_count, 0)
