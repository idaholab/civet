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
from django.test import TestCase, Client, RequestFactory
from django.test import override_settings
from django.urls import reverse
from ci import oauth_api
from ci.tests import utils
import json


@override_settings(INSTALLED_GITSERVERS=[utils.github_config()])
class OAuthTestCase(TestCase):
    def test_update_session_token(self):
        """
        Just get some coverage on the inner token updater functions.
        """
        self.client = Client()
        user = utils.get_test_user()
        oauth = user.auth()
        oauth._token_key = "token_key"
        oauth._client_id = "client_id"
        oauth._secret_id = "secret_id"
        oauth._user_key = "user_key"
        oauth._server_type = user.server.host_type
        session = self.client.session
        session[oauth._user_key] = user.name
        session.save()

        token_json = {"token": "new token"}
        oauth_api.update_session_token(session, oauth, token_json)
        user.refresh_from_db()
        self.assertEqual(user.token, json.dumps(token_json))
        self.assertEqual(session[oauth._token_key], token_json)

    def test_safe_redirect_url_same_origin(self):
        """
        A same-origin next URL (path only) must be honoured unchanged.
        """
        factory = RequestFactory()
        request = factory.get("/", SERVER_NAME="testserver")
        user = utils.get_test_user()
        auth = user.auth()

        safe_url = reverse("ci:main")
        result = auth._safe_redirect_url(request, safe_url)
        self.assertEqual(result, safe_url)

    def test_safe_redirect_url_external_rejected(self):
        """
        An absolute URL pointing to a different host must be rejected
        and the fallback returned instead.
        """
        factory = RequestFactory()
        request = factory.get("/", SERVER_NAME="testserver")
        user = utils.get_test_user()
        auth = user.auth()

        evil_url = "https://evil.example.com/steal-credentials"
        result = auth._safe_redirect_url(request, evil_url, fallback="ci:main")
        self.assertEqual(result, "ci:main")

    def test_safe_redirect_url_empty_falls_back(self):
        """
        When next_url is None or empty the fallback must be returned.
        """
        factory = RequestFactory()
        request = factory.get("/", SERVER_NAME="testserver")
        user = utils.get_test_user()
        auth = user.auth()

        for empty in (None, ""):
            result = auth._safe_redirect_url(request, empty, fallback="ci:main")
            self.assertEqual(result, "ci:main")
