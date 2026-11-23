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
from django.test import TestCase, RequestFactory, Client
from django.urls import reverse
from django.conf import settings
from django.test import override_settings
from ci import models
from ci.tests import utils
from mock import patch
from requests_oauthlib import OAuth2Session
import json
from django.contrib.messages import get_messages
from ci.oauth_api import OAuth


@override_settings(INSTALLED_GITSERVERS=[utils.gitlab_config()])
class Tests(TestCase):
    def setUp(self):
        self.client = Client()
        self.factory = RequestFactory()
        self.server = utils.create_git_server(host_type=settings.GITSERVER_GITLAB)
        self.oauth = self.server.auth()

    def test_sign_in(self):
        url = reverse("ci:gitlab:sign_in", args=[self.server.name])
        response = self.client.get(url)
        self.assertIn(self.oauth._state_key, self.client.session)
        state = self.client.session[self.oauth._state_key]
        self.assertIn(state, response.url)
        self.assertIn("state=", response.url)
        self.assertIn("scope=read_user&", response.url)
        self.assertEqual(self.client.session[self.oauth._scope_key], ["read_user"])

        # already signed in
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)  # redirect

        session = self.client.session
        session[self.oauth._token_key] = {
            "access_token": "1234",
            "token_type": "bearer",
            "scope": "api",
        }
        session.save()
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)  # redirect

    def test_sign_out(self):
        session = self.client.session
        auth = self.server.auth()
        session[auth._token_key] = "token"
        session[auth._state_key] = "state"
        session[auth._user_key] = "user"
        session.save()
        url = reverse("ci:gitlab:sign_out", args=[self.server.name])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)  # redirect
        # make sure the session variables are gone
        self.assertNotIn(auth._token_key, self.client.session)
        self.assertNotIn(auth._state_key, self.client.session)
        self.assertNotIn(auth._user_key, self.client.session)

        data = {"source_url": reverse("ci:main")}
        response = self.client.get(url, data)
        self.assertEqual(response.status_code, 302)  # redirect

    @patch.object(OAuth2Session, "fetch_token")
    @patch.object(OAuth2Session, "get")
    def test_callback(self, mock_get, mock_fetch_token):
        user = utils.get_test_user(server=self.server)
        auth = self.server.auth()
        mock_fetch_token.return_value = {
            "access_token": "1234",
            "token_type": "bearer",
            "scope": "api",
        }
        mock_get.return_value = utils.Response({auth._callback_user_key: user.name})

        session = self.client.session
        session[auth._state_key] = "state"
        session.save()
        url = reverse("ci:gitlab:callback", args=[self.server.name])
        response = self.client.post(url)
        self.assertEqual(response.status_code, 302)

        mock_fetch_token.side_effect = Exception("Bam!")
        url = reverse("ci:gitlab:callback", args=[self.server.name])
        response = self.client.post(url)
        self.assertEqual(response.status_code, 302)

    def _callback(self, mock_start_session, mock_fetch_token, username, scope):
        """
        Calls the callback, where GitLab authorized scope for username
        """
        oauth = self.oauth

        def fetch_token(request):
            request.session[oauth._token_key] = {"access_token": "1234", "scope": scope}

        mock_fetch_token.side_effect = fetch_token
        mock_start_session.return_value.get.return_value = utils.Response(
            {oauth._callback_user_key: username}
        )
        session = self.client.session
        session[oauth._state_key] = "state"
        session.save()
        url = reverse("ci:gitlab:callback", args=[self.server.name])
        return self.client.get(url)

    @patch.object(OAuth, "fetch_token")
    @patch.object(OAuth, "start_session")
    def test_callback_build_scope(self, mock_start_session, mock_fetch_token):
        """
        A build user without a stored token with the api scope is asked to
        authorize it before they are signed in
        """
        user = utils.get_test_user(server=self.server)
        utils.create_recipe(user=user)
        user.token = json.dumps({"access_token": "old", "scope": "read_api"})
        user.save()
        oauth = self.oauth

        response = self._callback(
            mock_start_session, mock_fetch_token, user.name, "read_user"
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("scope=api&", response.url)
        session = self.client.session
        self.assertNotIn(oauth._user_key, session)
        self.assertNotIn(oauth._token_key, session)
        self.assertEqual(session[oauth._pending_user_key], user.name)
        self.assertEqual(session[oauth._scope_key], ["api"])
        user.refresh_from_db()
        self.assertIn("read_api", user.token)

        # Authorizing the api scope signs them in and stores the token
        response = self._callback(
            mock_start_session, mock_fetch_token, user.name, "api"
        )
        self.assertEqual(response.url, reverse("ci:main"))
        session = self.client.session
        self.assertEqual(session[oauth._user_key], user.name)
        self.assertNotIn(oauth._pending_user_key, session)
        user.refresh_from_db()
        self.assertEqual(json.loads(user.token)["scope"], "api")

        # Now that the stored token has the api scope, signing in with the
        # read scope doesn't ask again or replace the stored token
        self.client.get(reverse("ci:gitlab:sign_out", args=[self.server.name]))
        response = self._callback(
            mock_start_session, mock_fetch_token, user.name, "read_user"
        )
        self.assertEqual(response.url, reverse("ci:main"))
        self.assertEqual(self.client.session[oauth._user_key], user.name)
        user.refresh_from_db()
        self.assertEqual(json.loads(user.token)["scope"], "api")

    @patch.object(OAuth, "fetch_token")
    @patch.object(OAuth, "start_session")
    def test_callback_build_scope_other_user(
        self, mock_start_session, mock_fetch_token
    ):
        """
        The api scope must be authorized by the same user that signed in
        """
        user = utils.get_test_user(server=self.server)
        utils.create_recipe(user=user)
        user.token = ""
        user.save()
        oauth = self.oauth
        self._callback(mock_start_session, mock_fetch_token, user.name, "read_user")
        self.assertEqual(self.client.session[oauth._pending_user_key], user.name)

        response = self._callback(mock_start_session, mock_fetch_token, "other", "api")
        self.assertEqual(response.status_code, 302)
        session = self.client.session
        self.assertNotIn(oauth._user_key, session)
        self.assertNotIn(oauth._token_key, session)
        self.assertNotIn(oauth._pending_user_key, session)
        messages = [str(m) for m in get_messages(response.wsgi_request)]
        self.assertIn('Authorized as "other" instead of "%s"' % user.name, messages[0])
        user.refresh_from_db()
        self.assertEqual(user.token, "")
        self.assertFalse(models.GitUser.objects.filter(name="other").exists())

    @patch.object(OAuth, "fetch_token")
    @patch.object(OAuth, "start_session")
    def test_callback_not_build_user(self, mock_start_session, mock_fetch_token):
        """
        Users that aren't build users are signed in with the read scope
        """
        oauth = self.oauth
        response = self._callback(
            mock_start_session, mock_fetch_token, "newUser", "read_user"
        )
        self.assertEqual(response.url, reverse("ci:main"))
        session = self.client.session
        self.assertEqual(session[oauth._user_key], "newUser")
        self.assertNotIn(oauth._pending_user_key, session)
        self.assertEqual(models.GitUser.objects.get(name="newUser").token, "")

        # An existing user that isn't a build user
        self.client.get(reverse("ci:gitlab:sign_out", args=[self.server.name]))
        response = self._callback(
            mock_start_session, mock_fetch_token, "newUser", "read_user"
        )
        self.assertEqual(response.url, reverse("ci:main"))
        session = self.client.session
        self.assertEqual(session[oauth._user_key], "newUser")
        self.assertNotIn(oauth._pending_user_key, session)

    def test_sign_in_clears_pending_user(self):
        """
        Signing in again starts over after an unfinished build scope request
        """
        session = self.client.session
        session[self.oauth._pending_user_key] = "someone"
        session.save()
        response = self.client.get(
            reverse("ci:gitlab:sign_in", args=[self.server.name])
        )
        self.assertIn("scope=read_user&", response.url)
        self.assertNotIn(self.oauth._pending_user_key, self.client.session)

    def test_session(self):
        user = utils.get_test_user(server=self.server)
        auth = user.auth()
        self.assertEqual(auth.start_session(self.client.session), None)

        session = self.client.session
        self.assertFalse(auth.is_signed_in(session))
        session[auth._user_key] = "no_user"
        session.save()
        self.assertFalse(auth.is_signed_in(session))
        session[auth._token_key] = "token"
        session.save()
        self.assertTrue(auth.is_signed_in(session))
        self.assertEqual(auth.signed_in_user(user.server, session), None)
        self.assertNotEqual(auth.start_session(session), None)

        session[auth._user_key] = user.name
        session.save()
        self.assertEqual(auth.signed_in_user(user.server, session), user)
        self.assertNotEqual(auth.user_token_to_oauth_token(user), None)
        user2 = utils.create_user(server=self.server)
        self.assertEqual(auth.user_token_to_oauth_token(user2), None)

        self.assertNotEqual(auth.start_session_for_user(user), None)

        auth.set_browser_session_from_user(session, user)
        session.save()
        self.assertEqual(session[auth._user_key], user.name)
