# Copyright 2016-2025 Battelle Energy Alliance, LLC
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
import copy, json, requests
from . import utils
from django.test import override_settings
from ci.tests import utils as test_utils
from client import JobGetter, BaseClient
from mock import patch
from ci.tests import DBTester

BaseClient.setup_logger()

good_response = {
    "job_id": 1234,
    "config": "config",
    "success": True,
    "message": "message",
    "status": "ok",
    "job_info": {},
}


@override_settings(INSTALLED_GITSERVERS=[test_utils.github_config()])
class Tests(DBTester.DBTester):
    def create_getter(self):
        self.client_info = utils.default_client_info()
        getter = JobGetter.JobGetter(self.client_info)
        return getter

    def test_check_response(self):
        g = self.create_getter()

        # good response
        self.assertEqual(g.check_response(good_response), True)

        # missing a key
        for key in good_response:
            response = copy.deepcopy(good_response)
            del response[key]
            self.assertEqual(g.check_response(response), False)

        # wrong type
        for key in good_response:
            response = copy.deepcopy(good_response)
            response[key] = 1234.5
            self.assertEqual(g.check_response(response), False)

        # have an extra key
        response = copy.deepcopy(good_response)
        response["foo"] = "bar"
        self.assertEqual(g.check_response(response), False)

    @patch.object(requests, "post")
    def test_get_job(self, mock_post):
        g = self.create_getter()

        # good response
        mock_post.return_value = test_utils.Response(good_response)
        response = g.get_job()
        self.assertIsNotNone(response)
        # Sends the key for the server
        post_data = json.loads(mock_post.call_args[0][1])
        self.assertEqual(post_data["build_key"], "key0")
        self.assertNotIn("build_keys", post_data)

        # The old response with the key isn't accepted
        mock_post.return_value = test_utils.Response(
            dict(good_response, build_key=1234)
        )
        self.assertIsNone(g.get_job())

        # threw on post
        mock_post.return_value = test_utils.Response(good_response, do_raise=True)
        self.assertIsNone(g.get_job())

        # bad values
        response = copy.deepcopy(good_response)
        del response["job_id"]
        mock_post.return_value = test_utils.Response(response)
        self.assertIsNone(g.get_job())

        # Job not available
        response = copy.deepcopy(good_response)
        response["job_id"] = None
        mock_post.return_value = test_utils.Response(response)
        self.assertIsNone(g.get_job())
