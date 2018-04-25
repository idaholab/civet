
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
from ci import models
from ci.tests import utils
from os import path
from mock import patch
import json
from django.test import override_settings
from ci.tests import DBTester
from requests_oauthlib import OAuth2Session

@override_settings(INSTALLED_GITSERVERS=[utils.github_config()])
class Tests(DBTester.DBTester):
    def setUp(self):
        super(Tests, self).setUp()
        self.create_default_recipes()

    def get_data(self, fname):
        p = '{}/{}'.format(path.dirname(__file__), fname)
        with open(p, 'r') as f:
            contents = f.read()
            return contents

    def client_post_json(self, url, data):
        json_data = json.dumps(data)
        return self.client.post(url, json_data, content_type='application/json')

    def test_webhook(self):
        url = reverse('ci:github:webhook', args=[10000])
        # only post allowed
        response = self.client.get(url)
        self.assertEqual(response.status_code, 405) # not allowed

        # no user
        response = self.client.post(url)
        self.assertEqual(response.status_code, 400)

        # no json
        user = utils.get_test_user()
        url = reverse('ci:github:webhook', args=[user.build_key])
        data = {'key': 'value'}
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 400)

        # bad json
        user = utils.get_test_user()
        url = reverse('ci:github:webhook', args=[user.build_key])
        response = self.client_post_json(url, data)
        self.assertEqual(response.status_code, 400)

    @patch.object(OAuth2Session, 'post')
    @patch.object(OAuth2Session, 'get')
    @patch.object(OAuth2Session, 'delete')
    def test_pull_request(self, mock_del, mock_get, mock_post):
        url = reverse('ci:github:webhook', args=[self.build_user.build_key])
        changed_files = utils.Response([{"filename": "foo"}])
        mock_get.return_value = changed_files
        mock_del.return_value = utils.Response()
        mock_post.return_value = utils.Response()
        data = self.get_data('pr_open_01.json')
        py_data = json.loads(data)
        py_data['pull_request']['base']['repo']['owner']['login'] = self.owner.name
        py_data['pull_request']['base']['repo']['name'] = self.repo.name
        py_data['pull_request']['title'] = '[WIP] testTitle'

        # no events or jobs on a work in progress
        self.set_counts()
        response = self.client_post_json(url, py_data)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"OK")
        self.compare_counts(num_git_events=1)
        self.assertEqual(mock_get.call_count, 0)
        self.assertEqual(mock_del.call_count, 0)
        self.assertEqual(mock_post.call_count, 0)

        # no events or jobs on a work in progress
        py_data['pull_request']['title'] = 'WIP: testTitle'
        self.set_counts()
        response = self.client_post_json(url, py_data)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"OK")
        self.compare_counts(num_git_events=1)
        self.assertEqual(mock_get.call_count, 0)
        self.assertEqual(mock_del.call_count, 0)
        self.assertEqual(mock_post.call_count, 0)

        # should produce a job and an event
        py_data['pull_request']['title'] = 'testTitle'
        self.set_counts()
        mock_get.call_count = 0
        response = self.client_post_json(url, py_data)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"OK")
        self.compare_counts(jobs=2,
                ready=1,
                events=1,
                commits=2,
                users=1,
                repos=1,
                branches=1,
                prs=1,
                active=2,
                active_repos=1,
                num_git_events=1,
                )
        ev = models.Event.objects.latest()
        self.assertEqual(ev.trigger_user, py_data['pull_request']['user']['login'])
        self.assertEqual(mock_get.call_count, 1) # for changed files
        self.assertEqual(mock_del.call_count, 0)
        self.assertEqual(mock_post.call_count, 0)

        # should just close the event
        py_data['action'] = 'closed'
        mock_get.call_count = 0
        self.set_counts()
        response = self.client_post_json(url, py_data)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"OK")
        self.compare_counts(pr_closed=True, num_git_events=1)
        self.assertEqual(mock_get.call_count, 1) # for changed files
        self.assertEqual(mock_del.call_count, 0)
        self.assertEqual(mock_post.call_count, 0)

        # should just open the same event
        py_data['action'] = 'reopened'
        mock_get.call_count = 0
        self.set_counts()
        response = self.client_post_json(url, py_data)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"OK")
        self.compare_counts(num_git_events=1)
        self.assertEqual(mock_get.call_count, 1) # for changed files
        self.assertEqual(mock_del.call_count, 0)
        self.assertEqual(mock_post.call_count, 0)

        # nothing should change
        py_data['action'] = 'labeled'
        mock_get.call_count = 0
        self.set_counts()
        response = self.client_post_json(url, py_data)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"OK")
        self.compare_counts(num_git_events=1)
        self.assertEqual(mock_get.call_count, 0)
        self.assertEqual(mock_del.call_count, 0)
        self.assertEqual(mock_post.call_count, 0)

        # nothing should change
        py_data['action'] = 'bad_action'
        self.set_counts()
        response = self.client_post_json(url, py_data)
        self.assertEqual(response.status_code, 400)
        self.assertIn(b"bad_action", response.content)
        self.compare_counts(num_git_events=1)
        self.assertEqual(mock_get.call_count, 0)
        self.assertEqual(mock_del.call_count, 0)
        self.assertEqual(mock_post.call_count, 0)

        # on synchronize we also remove labels on the PR
        py_data['action'] = 'synchronize'
        with self.settings(INSTALLED_GITSERVERS=[utils.github_config(remote_update=True)]):
            label_name = self.server.server_config()["remove_pr_label_prefix"][0]
            mock_get.return_value = None
            remove_label = utils.Response([{"name": label_name}])
            mock_get.side_effect = [remove_label, changed_files]
            mock_del.return_value = utils.Response()
            self.set_counts()
            response = self.client_post_json(url, py_data)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.content, b"OK")
            self.compare_counts(num_git_events=1)
            self.assertEqual(mock_get.call_count, 2) # 1 for changed files, 1 in remove_pr_todo_labels
            self.assertEqual(mock_del.call_count, 1) # for remove_pr_todo_labels
            self.assertEqual(mock_post.call_count, 0)

            # new sha, new event
            py_data['pull_request']['head']['sha'] = '2345'
            mock_get.side_effect = [remove_label, changed_files]
            mock_get.call_count = 0
            mock_del.call_count = 0
            self.set_counts()
            response = self.client_post_json(url, py_data)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.content, b"OK")
            self.compare_counts(jobs=2,
                    ready=1,
                    events=1,
                    commits=1,
                    active=2,
                    canceled=2,
                    events_canceled=1,
                    num_changelog=2,
                    num_events_completed=1,
                    num_jobs_completed=2,
                    num_git_events=1,
                    )
            self.assertEqual(mock_del.call_count, 1)
            self.assertEqual(mock_get.call_count, 2) # 1 for changed files, 1 in remove_pr_todo_labels
            self.assertEqual(mock_post.call_count, 4) # 2 previous jobs cancel status, 2 new jobs pending status

    @patch.object(OAuth2Session, 'post')
    @patch.object(OAuth2Session, 'get')
    @patch.object(OAuth2Session, 'delete')
    def test_push(self, mock_del, mock_get, mock_post):
        url = reverse('ci:github:webhook', args=[self.build_user.build_key])
        data = self.get_data('push_01.json')
        py_data = json.loads(data)
        py_data['repository']['owner']['name'] = self.owner.name
        py_data['repository']['name'] = self.repo.name
        py_data['ref'] = 'refs/heads/{}'.format(self.branch.name)

        # Everything OK
        self.set_counts()
        response = self.client_post_json(url, py_data)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"OK")
        self.compare_counts(jobs=2, ready=1, events=1, commits=2, active=2, active_repos=1, num_git_events=1)
        ev = models.Event.objects.latest()
        self.assertEqual(ev.cause, models.Event.PUSH)
        self.assertEqual(ev.description, "Update README.md")
        self.assertEqual(mock_del.call_count, 0)
        self.assertEqual(mock_get.call_count, 0)
        self.assertEqual(mock_post.call_count, 0)

        py_data['head_commit']['message'] = "Merge commit '123456789'"
        py_data['after'] = '123456789'
        py_data['before'] = '1'
        self.set_counts()
        response = self.client_post_json(url, py_data)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"OK")
        self.compare_counts(jobs=2, ready=1, events=1, commits=2, active=2, num_git_events=1)
        ev = models.Event.objects.latest()
        self.assertEqual(ev.description, "Merge commit 123456")
        self.assertEqual(mock_del.call_count, 0)
        self.assertEqual(mock_get.call_count, 0)
        self.assertEqual(mock_post.call_count, 0)

    def test_zen(self):
        url = reverse('ci:github:webhook', args=[self.build_user.build_key])
        data = self.get_data('ping.json')
        py_data = json.loads(data)
        self.set_counts()
        response = self.client_post_json(url, py_data)
        self.assertEqual(response.status_code, 200)
        self.compare_counts(num_git_events=1)

    @patch.object(OAuth2Session, 'post')
    @patch.object(OAuth2Session, 'get')
    @patch.object(OAuth2Session, 'delete')
    def test_release(self, mock_del, mock_get, mock_post):
        jdata = [{"name": "1.0",
                "commit": {"sha": "1234"},
                }]
        mock_get.return_value = utils.Response(jdata)
        url = reverse('ci:github:webhook', args=[self.build_user.build_key])
        data = self.get_data('release.json')
        py_data = json.loads(data)
        py_data['repository']['owner']['login'] = self.owner.name
        py_data['repository']['name'] = self.repo.name
        py_data['release']['target_commitish'] = self.branch.name
        self.set_counts()
        response = self.client_post_json(url, py_data)
        self.assertEqual(response.status_code, 200)
        self.compare_counts(num_git_events=1)
        self.assertEqual(mock_del.call_count, 0)
        self.assertEqual(mock_get.call_count, 1) # getting SHA
        self.assertEqual(mock_post.call_count, 0)

        # The commit could be a hash, then we assume the branch is master
        py_data['release']['target_commitish'] = "1"*40
        mock_get.call_count = 0
        self.set_counts()
        response = self.client_post_json(url, py_data)
        self.assertEqual(response.status_code, 200)
        self.compare_counts(num_git_events=1)
        self.assertEqual(mock_del.call_count, 0)
        self.assertEqual(mock_get.call_count, 0)
        self.assertEqual(mock_post.call_count, 0)

        rel = utils.create_recipe(name="Release1",
                user=self.build_user,
                repo=self.repo,
                branch=self.branch,
                cause=models.Recipe.CAUSE_RELEASE,
                )
        rel1 = utils.create_recipe(name="Release with dep",
                user=self.build_user,
                repo=self.repo,
                branch=self.branch,
                cause=models.Recipe.CAUSE_RELEASE,
                )
        rel1.depends_on.add(rel)

        py_data['release']['target_commitish'] = self.branch.name
        self.set_counts()
        response = self.client_post_json(url, py_data)
        self.assertEqual(response.status_code, 200)
        self.compare_counts(events=1, commits=1, jobs=2, ready=1, active=2, num_git_events=1)
        self.assertEqual(mock_del.call_count, 0)
        self.assertEqual(mock_get.call_count, 1) # getting SHA
        self.assertEqual(mock_post.call_count, 0)

        mock_get.call_count = 0
        mock_get.side_effect = Exception("Bam!")
        self.set_counts()
        response = self.client_post_json(url, py_data)
        self.assertEqual(response.status_code, 400)
        self.compare_counts(num_git_events=1)
        self.assertEqual(mock_del.call_count, 0)
        self.assertEqual(mock_get.call_count, 1) # getting SHA
        self.assertEqual(mock_post.call_count, 0)
