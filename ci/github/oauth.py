
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

class GitHubAuth(OAuth):
  def __init__(self):
    super(GitHubAuth, self).__init__()
    self._prefix = 'github_'
    self._token_key = 'github_token'
    self._user_key = 'github_user'
    self._state_key = 'github_state'
    self._collaborators_key = 'github_collaborators'
    self._client_id = settings.GITHUB_CLIENT_ID
    self._secret_id = settings.GITHUB_SECRET_ID
    self._server_type = settings.GITSERVER_GITHUB
    self._api_url = 'https://github.com'
    self._token_url = '{}/login/oauth/access_token'.format(self._api_url)
    self._auth_url = '{}/login/oauth/authorize'.format(self._api_url)
    self._user_url = 'https://api.github.com/user'
    self._callback_user_key = 'login'
    self._scope = ['repo',]

def sign_in(request):
  return GitHubAuth().sign_in(request)

def sign_out(request):
  return GitHubAuth().sign_out(request)

def callback(request):
  return GitHubAuth().callback(request)
