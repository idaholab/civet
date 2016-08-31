
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

from django.conf import settings
from ci.oauth_api import OAuth

class BitBucketAuth(OAuth):
  """
  OAuth2 with BitBucket.
  Some changes to the base OAuth implementation were required.
  BitBucket requires user/password authentication ( which are the client/secret ).
  Tokens are set to expire after an hour so the refresh token mechanisms needed
  to be put in place.
  These changes don't seem to affect GitHub.
  """
  def __init__(self):
    super(BitBucketAuth, self).__init__()
    self._prefix = 'bitbucket_'
    self._token_key = 'bitbucket_token'
    self._user_key = 'bitbucket_user'
    self._state_key = 'bitbucket_state'
    self._client_id = settings.BITBUCKET_CLIENT_ID
    self._secret_id = settings.BITBUCKET_SECRET_ID
    self._server_type = settings.GITSERVER_BITBUCKET
    self._collaborators_key = 'bitbucket_collaborators'
    self._api_url = 'https://bitbucket.org'
    self._token_url = '{}/site/oauth2/access_token'.format(self._api_url)
    self._auth_url = '{}/site/oauth2/authorize'.format(self._api_url)
    self._user_url = 'https://api.bitbucket.org/2.0/user'
    self._callback_user_key = 'username'
    self._scope = None

def sign_in(request):
  return BitBucketAuth().sign_in(request)

def sign_out(request):
  return BitBucketAuth().sign_out(request)

def callback(request):
  return BitBucketAuth().callback(request)
