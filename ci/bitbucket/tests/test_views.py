
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
from django.conf import settings
from ci import models
from ci.tests import utils
from os import path
import json
from ci.tests import DBTester

@override_settings(INSTALLED_GITSERVERS=[utils.bitbucket_config()])
class Tests(DBTester.DBTester):
    def setUp(self):
        super(Tests, self).setUp()
        self.create_default_recipes(server_type=settings.GITSERVER_BITBUCKET)

    def get_data(self, fname):
        p = '{}/{}'.format(path.dirname(__file__), fname)
        with open(p, 'r') as f:
            contents = f.read()
            return contents

    def client_post_json(self, url, data):
        json_data = json.dumps(data)
        return self.client.post(url, json_data, content_type='application/json')

    def test_webhook(self):
        url = reverse('ci:bitbucket:webhook', args=[10000])
        # only post allowed
        response = self.client.get(url)
        self.assertEqual(response.status_code, 405) # not allowed
        self.assertNotEqual(response.content, b"OK")

        # no user
        data = {'key': 'value'}
        response = self.client_post_json(url, data)
        self.assertEqual(response.status_code, 400)
        self.assertNotEqual(response.content, b"OK")

        # not json
        user = utils.get_test_user(server=self.server)
        url = reverse('ci:bitbucket:webhook', args=[user.build_key])
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 400)
        self.assertNotEqual(response.content, b"OK")

        # user with no recipes
        response = self.client_post_json(url, data)
        self.assertEqual(response.status_code, 400)
        self.assertNotEqual(response.content, b"OK")

        # unknown json
        utils.create_recipe(user=user)
        response = self.client_post_json(url, data)
        self.assertEqual(response.status_code, 400)

    def test_pull_request(self):
        url = reverse('ci:bitbucket:webhook', args=[self.build_user.build_key])
        data = self.get_data('pr_open_01.json')
        py_data = json.loads(data)
        py_data['pullrequest']['destination']['repository']['name'] = self.repo.name
        py_data['pullrequest']['destination']['repository']['full_name'] = "%s/%s" % (self.repo.user.name, self.repo.name)
        py_data['pullrequest']['destination']['branch']['name'] = self.branch.name

        self.set_counts()
        response = self.client_post_json(url, py_data)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"OK")
        self.compare_counts(jobs=2, ready=1, events=1, commits=2, users=1, repos=1, branches=1, prs=1, active=2, active_repos=1)

        py_data['pullrequest']['state'] = 'DECLINED'
        self.set_counts()
        response = self.client_post_json(url, py_data)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"OK")
        self.compare_counts(pr_closed=True)

        py_data['pullrequest']['state'] = 'BadState'
        self.set_counts()
        response = self.client_post_json(url, py_data)
        self.assertEqual(response.status_code, 400)
        self.assertNotEqual(response.content, b"OK")
        self.compare_counts(pr_closed=True)

    def test_push(self):
        url = reverse('ci:bitbucket:webhook', args=[self.build_user.build_key])
        data = self.get_data('push_01.json')
        py_data = json.loads(data)
        py_data['actor']['username'] = self.build_user.name
        py_data['repository']['name'] = self.repo.name
        py_data['repository']['owner']['username'] = self.repo.user.name
        py_data['push']['changes'][-1]['new']['name'] = self.branch.name

        # Everything OK
        self.set_counts()
        response = self.client_post_json(url, py_data)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"OK")
        self.compare_counts(jobs=2, ready=1, events=1, commits=2, active=2, active_repos=1)
        ev = models.Event.objects.latest()
        self.assertEqual(ev.cause, models.Event.PUSH)
        self.assertEqual(ev.description, "Update README.md")

        # Do it again, nothing should change
        self.set_counts()
        response = self.client_post_json(url, py_data)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"OK")
        self.compare_counts()

        # Sometimes the new data isn't there
        del py_data['push']['changes'][-1]['new']
        self.set_counts()
        response = self.client_post_json(url, py_data)
        self.assertEqual(response.status_code, 400)
        self.assertNotEqual(response.content, b"OK")
        self.compare_counts()

        # Sometimes the old data isn't there
        del py_data['push']['changes'][-1]['old']
        self.set_counts()
        response = self.client_post_json(url, py_data)
        self.assertEqual(response.status_code, 400)
        self.assertNotEqual(response.content, b"OK")
        self.compare_counts()
