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
from django.contrib.messages import get_messages
from django.test import TestCase, Client, RequestFactory
from django.test import override_settings
from django.urls import reverse
from mock import patch
from unittest.mock import MagicMock
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

    def test_not_configured(self):
        """
        A git server that isn't in INSTALLED_GITSERVERS can't be used.
        """
        server = utils.create_git_server(name="not_configured")
        with self.assertRaises(oauth_api.OAuthException):
            oauth_api.OAuth(server=server)

    def test_start_session_token_updater(self):
        """
        The token updater for the browser session should update the
        session and the user's token.
        """
        user = utils.get_test_user()
        oauth = user.auth()
        session = {}
        self.assertIsNone(oauth.start_session(session))

        session[oauth._user_key] = user.name
        session[oauth._token_key] = json.loads(user.token)
        oauth_session = oauth.start_session(session)
        token_json = {"access_token": "new token", "token_type": "bearer"}
        oauth_session.token_updater(token_json)
        user.refresh_from_db()
        self.assertEqual(user.token, json.dumps(token_json))
        self.assertEqual(session[oauth._token_key], token_json)

    def test_start_session_for_user_token_updater(self):
        """
        The token updater for a user session should update the user's token.
        """
        user = utils.get_test_user()
        oauth = user.auth()
        oauth_session = oauth.start_session_for_user(user)
        token_json = {"access_token": "new token", "token_type": "bearer"}
        oauth_session.token_updater(token_json)
        user.refresh_from_db()
        self.assertEqual(user.token, json.dumps(token_json))

    def test_get_json_value_invalid_json(self):
        user = utils.get_test_user()
        oauth = user.auth()
        response = MagicMock()
        response.json.side_effect = ValueError("Not JSON")
        with self.assertRaisesRegex(
            oauth_api.OAuthException, "Response did not contain JSON"
        ):
            oauth.get_json_value(response, "name")

    def test_fetch_token_no_state(self):
        """
        If the authorization procedure wasn't started then there
        isn't a state in the session.
        """
        user = utils.get_test_user()
        oauth = user.auth()
        request = RequestFactory().get("/")
        request.session = {}
        with self.assertRaisesRegex(
            oauth_api.OAuthException, "You have not completed the authorization"
        ):
            oauth.fetch_token(request)

    @patch.object(oauth_api.OAuth, "fetch_token")
    def test_callback_no_token(self, mock_fetch_token):
        """
        If fetching the token didn't store a token in the session
        then the user shouldn't get logged in.
        """
        user = utils.get_test_user()
        oauth = user.auth()
        url = reverse("ci:github:callback", args=[user.server.name])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(mock_fetch_token.call_count, 1)
        self.assertNotIn(oauth._user_key, self.client.session)
        messages = [str(m) for m in get_messages(response.wsgi_request)]
        self.assertEqual(messages, ["Couldn't get token when trying to log in"])

    @patch.object(oauth_api.OAuth, "fetch_token")
    @patch.object(oauth_api.OAuth, "start_session")
    def test_callback_cycles_session_key(self, mock_start_session, mock_fetch_token):
        """
        A session key that existed before signing in shouldn't
        become authenticated after signing in.
        """
        user = utils.get_test_user()
        oauth = user.auth()

        def fetch_token(request):
            request.session[oauth._token_key] = {"access_token": "1234"}

        mock_fetch_token.side_effect = fetch_token
        mock_start_session.return_value.get.return_value = utils.Response(
            {oauth._callback_user_key: user.name}
        )

        session = self.client.session
        session[oauth._state_key] = "state"
        session.save()
        old_key = session.session_key

        url = reverse("ci:github:callback", args=[user.server.name])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)

        new_session = self.client.session
        self.assertNotEqual(new_session.session_key, old_key)
        self.assertEqual(new_session[oauth._user_key], user.name)
        self.assertFalse(new_session.exists(old_key))
