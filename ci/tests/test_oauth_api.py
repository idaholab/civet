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
from django.conf import settings
from django.contrib.messages import get_messages
from django.test import TestCase, Client, RequestFactory
from django.test import override_settings
from django.urls import reverse
from mock import patch
from unittest.mock import MagicMock
from ci import models, oauth_api
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
        utils.create_recipe(user=user)
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
        session and the build user's token.
        """
        user = utils.get_test_user()
        utils.create_recipe(user=user)
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
        The token updater for a user session should update the build user's token.
        """
        user = utils.get_test_user()
        utils.create_recipe(user=user)
        oauth = user.auth()
        oauth_session = oauth.start_session_for_user(user)
        token_json = {"access_token": "new token", "token_type": "bearer"}
        oauth_session.token_updater(token_json)
        user.refresh_from_db()
        self.assertEqual(user.token, json.dumps(token_json))

    def test_update_user_token_not_build_user(self):
        """
        Only build users keep their token in the DB; the token of any
        other user is cleared instead of saved.
        """
        user = utils.get_test_user()
        self.assertFalse(user.needs_stored_token())
        self.assertNotEqual(user.token, "")
        oauth_api.update_user_token(user, {"access_token": "new token"})
        user.refresh_from_db()
        self.assertEqual(user.token, "")

        utils.create_webhook(build_user=user)
        self.assertTrue(user.needs_stored_token())
        oauth_api.update_user_token(user, {"access_token": "new token"})
        user.refresh_from_db()
        self.assertEqual(user.token, json.dumps({"access_token": "new token"}))

    def test_token_has_scope(self):
        self.assertTrue(oauth_api.token_has_scope({"scope": "read_api"}, None))
        self.assertTrue(oauth_api.token_has_scope(None, ["api"]))
        # Tokens that don't list a scope are assumed to have it
        self.assertTrue(oauth_api.token_has_scope({"access_token": "1"}, ["api"]))
        self.assertTrue(oauth_api.token_has_scope({"scope": "api"}, ["api"]))
        self.assertTrue(
            oauth_api.token_has_scope({"scope": ["read_api", "api"]}, "api")
        )
        self.assertFalse(
            oauth_api.token_has_scope({"scope": "read_user read_api"}, ["api"])
        )

    def test_update_user_token_build_scope(self):
        """
        A build user's token isn't replaced by one without the build scope
        """
        user = utils.get_test_user()
        utils.create_recipe(user=user)
        old_token = user.token
        read_token = {"access_token": "read", "scope": "read_user read_api"}
        oauth_api.update_user_token(user, read_token, build_scope=["api"])
        user.refresh_from_db()
        self.assertEqual(user.token, old_token)

        api_token = {"access_token": "api", "scope": "api"}
        oauth_api.update_user_token(user, api_token, build_scope=["api"])
        user.refresh_from_db()
        self.assertEqual(user.token, json.dumps(api_token))

        # Other users don't need the build scope
        other = utils.create_user_with_token(name="other", server=user.server)
        oauth_api.update_user_token(other, read_token, build_scope=["api"])
        other.refresh_from_db()
        self.assertEqual(other.token, "")

    def test_update_user(self):
        """
        Signing in only stores the token in the DB for build users, but
        always keeps it in the browser session.
        """
        user = utils.get_test_user()
        oauth = user.auth()
        token_json = {"access_token": "new token", "token_type": "bearer"}
        session = {oauth._user_key: user.name, oauth._token_key: token_json}
        oauth.update_user(session)
        user.refresh_from_db()
        self.assertEqual(user.token, "")
        self.assertEqual(session[oauth._token_key], token_json)

        utils.create_recipe(user=user)
        oauth.update_user(session)
        user.refresh_from_db()
        self.assertEqual(user.token, json.dumps(token_json))

        oauth.update_user({oauth._user_key: "newUser", oauth._token_key: token_json})
        new_user = models.GitUser.objects.get(name="newUser", server=user.server)
        self.assertEqual(new_user.token, "")

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
        # Signing in restores the default session expiry
        self.assertEqual(new_session.get_expiry_age(), settings.SESSION_COOKIE_AGE)

    def test_sign_in_session_expiry(self):
        """
        A session started by signing in expires quickly, so that crawlers
        that never finish signing in don't leave long lived sessions
        """
        user = utils.get_test_user()
        oauth = user.auth()
        url = reverse("ci:github:sign_in", args=[user.server.name])
        response = self.client.get(url, {"next": "/"})
        self.assertEqual(response.status_code, 302)
        session = self.client.session
        self.assertIn(oauth._state_key, session)
        self.assertEqual(session.get_expiry_age(), settings.SIGN_IN_SESSION_EXPIRY)
        self.assertLess(settings.SIGN_IN_SESSION_EXPIRY, settings.SESSION_COOKIE_AGE)
