
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

from django.test import TestCase, RequestFactory, Client
from django.core.urlresolvers import reverse
from django.conf import settings
from django.test import override_settings
from ci.tests import utils
import requests
from mock import patch

@override_settings(INSTALLED_GITSERVERS=[utils.gitlab_config()])
class Tests(TestCase):
    def setUp(self):
        self.client = Client()
        self.factory = RequestFactory()
        self.server = utils.create_git_server(host_type=settings.GITSERVER_GITLAB)

    class PostResponse(object):
        def __init__(self, data):
            self.data = data

        def json(self):
            return self.data

    @patch.object(requests, 'post')
    def test_sign_in(self, mock_post):
        url = reverse('ci:gitlab:sign_in', args=[self.server.name])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

        # bad response
        username_data = {'username': 'testUser', 'password': 'testPassword' }
        mock_post.return_value = self.PostResponse({'error_description': 'none'})
        response = self.client.post(url, username_data)
        self.assertEqual(response.status_code, 200)

        username_data = {'username': 'testUser', 'password': 'testPassword' }
        response_data = {'private_token': '1234', 'username': 'testUser'}
        mock_post.return_value = self.PostResponse(response_data)
        response = self.client.post(url, username_data)
        self.assertEqual(response.status_code, 302)

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
