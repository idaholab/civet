
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
from django.test import override_settings
from mock import patch
from requests_oauthlib import OAuth2Session
from ci import github, oauth_api
from ci.tests import utils
import json

@override_settings(INSTALLED_GITSERVERS=[utils.github_config()])
class Tests(TestCase):
    def setUp(self):
        self.client = Client()
        self.factory = RequestFactory()
        self.server = utils.create_git_server()
        self.oauth = self.server.auth()

    def test_sign_in(self):
        url = reverse('ci:github:sign_in', args=[self.server.name])
        response = self.client.get(url)
        self.assertIn(self.oauth._state_key, self.client.session)
        state = self.client.session[self.oauth._state_key]
        self.assertIn(state, response.url)
        self.assertIn('state', response.url)
        self.assertIn('repo', response.url)

        # already signed in
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302) # redirect

        session = self.client.session
        session[self.oauth._token_key] = {'access_token': '1234', 'token_type': 'bearer', 'scope': 'repo'}
        session.save()
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302) # redirect

    def test_update_user(self):
        user = utils.get_test_user()
        session = {self.oauth._token_key: json.loads(user.token), self.oauth._user_key: user.name}
        auth = self.server.auth()
        auth.update_user(session)
        user2 = utils.create_user()
        session[self.oauth._user_key] = user2.name
        auth.update_user(session)

    def test_get_json_value(self):
        with self.assertRaises(Exception):
            github.oauth.get_json_value(None, 'name')

        response = utils.Response({'name': 'value'})
        with self.assertRaises(oauth_api.OAuthException):
            auth = self.server.auth()
            auth.get_json_value(response, 'foo')

        val = auth.get_json_value(response, 'name')
        self.assertEqual(val, 'value')

    @patch.object(OAuth2Session, 'fetch_token')
    @patch.object(OAuth2Session, 'get')
    def test_callback(self, mock_get, mock_fetch_token):
        user = utils.get_test_user()
        auth = self.server.auth()
        mock_fetch_token.return_value = {'access_token': '1234', 'token_type': 'bearer', 'scope': 'repo'}
        mock_get.return_value = utils.Response({auth._callback_user_key: user.name})

        session = self.client.session
        session[auth._state_key] = 'state'
        session.save()
        url = reverse('ci:github:callback', args=[self.server.name])
        response = self.client.post(url)
        self.assertEqual(response.status_code, 302)

        mock_fetch_token.side_effect = Exception('Bam!')
        url = reverse('ci:github:callback', args=[self.server.name])
        response = self.client.post(url)
        self.assertEqual(response.status_code, 302)

    def test_sign_out(self):
        session = self.client.session
        session[self.oauth._token_key] = 'token'
        session[self.oauth._state_key] = 'state'
        session[self.oauth._user_key] = 'user'
        session.save()
        url = reverse('ci:github:sign_out', args=[self.server.name])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302) # redirect
        # make sure the session variables are gone
        self.assertNotIn(self.oauth._token_key, self.client.session)
        self.assertNotIn(self.oauth._state_key, self.client.session)
        self.assertNotIn(self.oauth._user_key, self.client.session)

        data = {'source_url': reverse('ci:main')}
        response = self.client.get(url, data)
        self.assertEqual(response.status_code, 302) # redirect

    def test_session(self):
        user = utils.get_test_user()
        oauth = self.server.auth()
        self.assertEqual(oauth.start_session(self.client.session), None)

        session = self.client.session
        self.assertFalse(oauth.is_signed_in(session))
        session[self.oauth._user_key] = 'no_user'
        session.save()
        self.assertFalse(oauth.is_signed_in(session))
        session[self.oauth._token_key] = 'token'
        session.save()
        self.assertTrue(oauth.is_signed_in(session))
        self.assertEqual(oauth.signed_in_user(user.server, session), None)
        self.assertNotEqual(oauth.start_session(session), None)

        session[self.oauth._user_key] = user.name
        session.save()
        self.assertEqual(oauth.signed_in_user(user.server, session), user)
        self.assertNotEqual(oauth.user_token_to_oauth_token(user), None)
        user2 = utils.create_user()
        self.assertEqual(oauth.user_token_to_oauth_token(user2), None)

        self.assertNotEqual(oauth.start_session_for_user(user), None)

        oauth.set_browser_session_from_user(session, user)
        session.save()
        self.assertEqual(session[self.oauth._user_key], user.name)
