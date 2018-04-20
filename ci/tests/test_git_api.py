
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

from django.test import override_settings
from ci.git_api import GitAPI
from ci.tests import utils
from mock import patch
from ci.tests import DBTester
import requests

@override_settings(INSTALLED_GITSERVERS=[utils.github_config()])
class Tests(DBTester.DBTester):
    def setUp(self):
        super(Tests, self).setUp()
        self.server = utils.create_git_server()
        self.api = self.server.api()

    def test_api(self):
        """
        GitAPI is just a base class for the actual git servers.
        You can't even instantiate an instance since it has
        abstract methods.
        """
        with self.assertRaises(TypeError):
            GitAPI()

    @patch.object(requests, 'patch')
    def test_patch(self, mock_patch):
        mock_patch.return_value = utils.Response()
        self.api.patch("url")
        self.assertIs(self.api._bad_response, False)
        self.assertEqual(self.api.errors(), [])

        mock_patch.side_effect = Exception("Bam!")
        self.api.patch("url")
        self.assertIs(self.api._bad_response, True)
        self.assertNotEqual(self.api.errors(), [])

    @patch.object(requests, 'put')
    def test_put(self, mock_put):
        mock_put.return_value = utils.Response()
        self.api.put("url")
        self.assertIs(self.api._bad_response, False)
        self.assertEqual(self.api.errors(), [])

        mock_put.side_effect = Exception("Bam!")
        self.api.put("url")
        self.assertIs(self.api._bad_response, True)
        self.assertNotEqual(self.api.errors(), [])

    @patch.object(requests, 'delete')
    def test_delete(self, mock_delete):
        mock_delete.return_value = utils.Response()
        self.api.delete("url")
        self.assertIs(self.api._bad_response, False)
        self.assertEqual(self.api.errors(), [])

        mock_delete.side_effect = Exception("Bam!")
        self.api.delete("url")
        self.assertIs(self.api._bad_response, True)
        self.assertNotEqual(self.api.errors(), [])

    @patch.object(requests, 'get')
    def test_get_all_pages(self, mock_get):
        response0 = utils.Response(["foo"], use_links=True)
        response1 = utils.Response(["bar"], use_links=True)
        response2 = Exception("Bam!")
        mock_get.side_effect = [response0, response1, response2]
        data = self.api.get_all_pages("url")
        self.assertEqual(data, ["foo", "bar"])

        data3 = {"key": "value"}
        response3 = utils.Response(data3, use_links=True)
        response4 = utils.Response(["list"])
        mock_get.side_effect = [response3, response4]
        data = self.api.get_all_pages("url")
        self.assertEqual(data, data3)
