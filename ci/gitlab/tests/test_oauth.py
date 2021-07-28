
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
from django.test import TestCase, RequestFactory, Client
from django.urls import reverse
from django.conf import settings
from django.test import override_settings
from ci.tests import utils
from mock import patch
from requests_oauthlib import OAuth2Session

@override_settings(INSTALLED_GITSERVERS=[utils.gitlab_config()])
class Tests(TestCase):
    def setUp(self):
        self.client = Client()
        self.factory = RequestFactory()
        self.server = utils.create_git_server(host_type=settings.GITSERVER_GITLAB)
        self.oauth = self.server.auth()

    def test_sign_in(self):
        url = reverse('ci:gitlab:sign_in', args=[self.server.name])
        response = self.client.get(url)
        self.assertIn(self.oauth._state_key, self.client.session)
        state = self.client.session[self.oauth._state_key]
        self.assertIn(state, response.url)
        self.assertIn('state=', response.url)
        self.assertIn('scope=api', response.url)

        # already signed in
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302) # redirect

        session = self.client.session
        session[self.oauth._token_key] = {'access_token': '1234', 'token_type': 'bearer', 'scope': 'api'}
        session.save()
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302) # redirect

    def test_sign_out(self):
        session = self.client.session
        auth = self.server.auth()
        session[auth._token_key] = 'token'
        session[auth._state_key] = 'state'
        session[auth._user_key] = 'user'
        session.save()
        url = reverse('ci:gitlab:sign_out', args=[self.server.name])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302) # redirect
        # make sure the session variables are gone
        self.assertNotIn(auth._token_key, self.client.session)
        self.assertNotIn(auth._state_key, self.client.session)
        self.assertNotIn(auth._user_key, self.client.session)

        data = {'source_url': reverse('ci:main')}
        response = self.client.get(url, data)
        self.assertEqual(response.status_code, 302) # redirect

    @patch.object(OAuth2Session, 'fetch_token')
    @patch.object(OAuth2Session, 'get')
    def test_callback(self, mock_get, mock_fetch_token):
        user = utils.get_test_user(server=self.server)
        auth = self.server.auth()
        mock_fetch_token.return_value = {'access_token': '1234', 'token_type': 'bearer', 'scope': 'api'}
        mock_get.return_value = utils.Response({auth._callback_user_key: user.name})

        session = self.client.session
        session[auth._state_key] = 'state'
        session.save()
        url = reverse('ci:gitlab:callback', args=[self.server.name])
        response = self.client.post(url)
        self.assertEqual(response.status_code, 302)

        mock_fetch_token.side_effect = Exception('Bam!')
        url = reverse('ci:gitlab:callback', args=[self.server.name])
        response = self.client.post(url)
        self.assertEqual(response.status_code, 302)

    def test_session(self):
        user = utils.get_test_user(server=self.server)
        auth = user.auth()
        self.assertEqual(auth.start_session(self.client.session), None)

        session = self.client.session
        self.assertFalse(auth.is_signed_in(session))
        session[auth._user_key] = 'no_user'
        session.save()
        self.assertFalse(auth.is_signed_in(session))
        session[auth._token_key] = 'token'
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
