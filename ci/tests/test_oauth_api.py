
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

from django.test import TestCase, Client
from django.test.client import RequestFactory
from ci import oauth_api
from ci.tests import utils
import json

class OAuthTestCase(TestCase):
    fixtures = ['base']

    def setUp(self):
        self.client = Client()
        self.factory = RequestFactory()

    def test_update_session_token(self):
        """
        Just get some coverage on the inner token updater functions.
        """
        user = utils.get_test_user()
        oauth = oauth_api.OAuth()
        oauth._token_key = 'token_key'
        oauth._client_id = 'client_id'
        oauth._secret_id = 'secret_id'
        oauth._user_key = 'user_key'
        oauth._server_type = user.server.host_type
        session = self.client.session
        session[oauth._user_key] = user.name
        session.save()

        token_json = {'token': 'new token'}
        oauth_api.update_session_token(session, oauth, token_json)
        user.refresh_from_db()
        self.assertEqual(user.token, json.dumps(token_json))
        self.assertEqual(session[oauth._token_key], token_json)
