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
from django.test import override_settings
from ci.git_api import GitAPI, ForbiddenException
from ci.tests import utils
from mock import patch
from ci.tests import DBTester
from unittest.mock import MagicMock
import requests


@override_settings(INSTALLED_GITSERVERS=[utils.github_config()])
class Tests(DBTester.DBTester):
    def setUp(self):
        super(Tests, self).setUp()
        self.server = utils.create_git_server()
        self.api = self.server.api()
        self.url = "%s/url" % self.api._api_url

    def test_api(self):
        """
        GitAPI is just a base class for the actual git servers.
        You can't even instantiate an instance since it has
        abstract methods.
        """
        with self.assertRaises(TypeError):
            GitAPI()

    @patch.object(requests, "patch")
    def test_patch(self, mock_patch):
        mock_patch.return_value = utils.Response()
        self.api.patch(self.url)
        self.assertIs(self.api._bad_response, False)
        self.assertEqual(self.api.errors(), [])

        mock_patch.side_effect = Exception("Bam!")
        self.api.patch(self.url)
        self.assertIs(self.api._bad_response, True)
        self.assertNotEqual(self.api.errors(), [])

    @patch.object(requests, "put")
    def test_put(self, mock_put):
        mock_put.return_value = utils.Response()
        self.api.put(self.url)
        self.assertIs(self.api._bad_response, False)
        self.assertEqual(self.api.errors(), [])

        mock_put.side_effect = Exception("Bam!")
        self.api.put(self.url)
        self.assertIs(self.api._bad_response, True)
        self.assertNotEqual(self.api.errors(), [])

    @patch.object(requests, "delete")
    def test_delete(self, mock_delete):
        mock_delete.return_value = utils.Response()
        self.api.delete(self.url)
        self.assertIs(self.api._bad_response, False)
        self.assertEqual(self.api.errors(), [])

        mock_delete.side_effect = Exception("Bam!")
        self.api.delete(self.url)
        self.assertIs(self.api._bad_response, True)
        self.assertNotEqual(self.api.errors(), [])

    @patch.object(requests, "get")
    def test_get_all_pages(self, mock_get):
        response0 = utils.Response(["foo"], use_links=True)
        response1 = utils.Response(["bar"], use_links=True)
        response2 = Exception("Bam!")
        mock_get.side_effect = [response0, response1, response2]
        data = self.api.get_all_pages(self.url)
        self.assertEqual(data, ["foo", "bar"])

        data3 = {"key": "value"}
        response3 = utils.Response(data3, use_links=True)
        response4 = utils.Response(["list"])
        mock_get.side_effect = [response3, response4]
        data = self.api.get_all_pages(self.url)
        self.assertEqual(data, data3)

    def test_check_url(self):
        """Test GitAPI._check_url()."""
        api_url = self.api._api_url
        self.assertEqual(api_url, "https://<api_url>")
        good = [
            "%s/repos/owner/repo/issues/1/comments" % api_url,
            "https://<API_URL>/foo",
            "https://<api_url>:443/foo",
        ]
        for url in good:
            self.api._errors = []
            self.assertTrue(self.api._check_url(url, "GET"), url)
            self.assertEqual(self.api.errors(), [])

        bad = [
            "https://attacker.example/c",
            "http://<api_url>/foo",
            "https://<api_url>:8443/foo",
            "https://<api_url>.attacker.example/foo",
            "https://<api_url>@attacker.example/foo",
            "//attacker.example/foo",
            "/repos/owner/repo",
            "url",
            "https://<api_url>:bad/foo",
            "",
            None,
        ]
        for url in bad:
            self.api._errors = []
            self.api._bad_response = False
            self.assertFalse(self.api._check_url(url, "GET"), url)
            self.assertIs(self.api._bad_response, True)
            self.assertEqual(len(self.api.errors()), 1)

        # Nothing is allowed without an API URL
        self.api._api_url = None
        self.assertFalse(self.api._check_url("https://<api_url>/foo", "GET"))

    @patch.object(requests, "delete")
    @patch.object(requests, "put")
    @patch.object(requests, "patch")
    @patch.object(requests, "post")
    @patch.object(requests, "get")
    def test_refuse_other_hosts(self, *mocks):
        """No request is sent to a URL that isn't on the API host."""
        url = "https://attacker.example/c"
        for method in ["get", "post", "patch", "put", "delete", "get_all_pages"]:
            self.api._errors = []
            self.assertIsNone(getattr(self.api, method)(url))
            self.assertIs(self.api._bad_response, True)
            self.assertEqual(len(self.api.errors()), 1)
            self.assertIn("Refusing", self.api.errors()[0])
        for mock in mocks:
            self.assertEqual(mock.call_count, 0)

    @patch.object(requests, "get")
    def test_get_all_pages_refuse_next(self, mock_get):
        """A "next" link to another host is not followed."""
        response0 = utils.Response(["foo"], use_links=True)
        response0.links = {"next": {"url": "https://attacker.example/next"}}
        mock_get.return_value = response0
        data = self.api.get_all_pages(self.url)
        self.assertEqual(data, ["foo"])
        self.assertEqual(mock_get.call_count, 1)
        self.assertIn("Refusing", self.api.errors()[0])

    def test_possibly_raise_forbidden(self):
        """Test GitAPI._possibly_raise_forbidden()."""
        # Not a HTTPError
        GitAPI._possibly_raise_forbidden(Exception("foo"), requests.Response())

        # HTTPError, but another code
        response = MagicMock(spec=requests.Response)
        response.status_code = 404
        GitAPI._possibly_raise_forbidden(requests.exceptions.HTTPError(), response)

        # Is forbidden
        response = MagicMock(spec=requests.Response)
        response.status_code = 403
        with self.assertRaises(ForbiddenException):
            GitAPI._possibly_raise_forbidden(requests.exceptions.HTTPError(), response)

    def test_check_response_raise_forbidden(self):
        """Test GitAPI._check_response() with raise_forbidden=True."""
        # Is okay
        response = MagicMock(spec=requests.Response)
        response.status_code = 200
        self.api._check_response(response, raise_forbidden=True)

        # Is forbidden
        response = MagicMock(spec=requests.Response)
        response.status_code = 403
        response.raise_for_status.side_effect = requests.exceptions.HTTPError(
            "403 Forbidden"
        )
        with self.assertRaises(ForbiddenException):
            self.api._check_response(response, raise_forbidden=True)

    def test_get_raise_forbidden(self):
        """Test GitAPI.get() with raise_forbidden=True."""
        response = MagicMock(spec=requests.Response)
        response.status_code = 403
        response.raise_for_status.side_effect = requests.exceptions.HTTPError(
            "403 Forbidden"
        )
        with (
            patch.object(requests, "get", return_value=response),
            self.assertRaises(ForbiddenException),
        ):
            self.api.get(self.url, raise_forbidden=True)

    def test_response_to_str(self):
        """Test GitAPI._response_to_str()."""
        response = utils.Response({"key": "value"}, status_code=404)
        self.assertEqual(
            self.api._response_to_str(response),
            'Status code: 404\nReason: some reason\nJSON response:\n{\n  "key": "value"\n}',
        )

        # Response without valid JSON
        response = MagicMock(spec=requests.Response)
        response.status_code = 500
        response.reason = "Internal Server Error"
        response.json.side_effect = requests.exceptions.JSONDecodeError("bad", "", 0)
        self.assertEqual(
            self.api._response_to_str(response),
            "Status code: 500\nReason: Internal Server Error\nJSON response:\nINVALID JSON",
        )

    def test_ssl_verify(self):
        """Certificate verification can't be turned off with ssl_cert."""
        self.assertIs(self.api._ssl_cert, True)
        self.assertEqual(self.api._ssl_verify("/path/to/ca.pem"), "/path/to/ca.pem")
        self.assertIs(self.api._ssl_verify(True), True)
        for value in [False, None, "", 0]:
            with self.assertLogs("ci", level="WARNING"):
                self.assertIs(self.api._ssl_verify(value), True, value)

    @patch.object(requests, "delete")
    @patch.object(requests, "put")
    @patch.object(requests, "patch")
    @patch.object(requests, "post")
    @patch.object(requests, "get")
    def test_requests_verify(self, *mocks):
        """Every request verifies the server's certificate."""
        for mock in mocks:
            mock.return_value = utils.Response()
        for method in ["get", "post", "patch", "put", "delete"]:
            getattr(self.api, method)(self.url)
        for mock in mocks:
            self.assertEqual(mock.call_count, 1)
            self.assertIs(mock.call_args.kwargs["verify"], True)
