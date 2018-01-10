
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

from ci.oauth_api import OAuth
from django.conf import settings
from django.core.urlresolvers import reverse

class GitHubAuth(OAuth):
    def __init__(self, hostname=None, server=None):
        super(GitHubAuth, self).__init__(hostname, settings.GITSERVER_GITHUB, server)
        self._api_url = self._config.get("html_url", "")
        self._token_url = "%s/login/oauth/access_token" % self._api_url
        self._auth_url = "%s/login/oauth/authorize" % self._api_url
        self._user_url = "%s/user" % self._config.get("api_url", "")
        self._callback_user_key = 'login'
        self._scope = ['repo',]
        callback_url = reverse("ci:github:callback", args=[self._config.get("hostname")])
        self._redirect_uri = "%s%s" % (self._config.get("civet_base_url", ""), callback_url)

def sign_in(request, host):
    return GitHubAuth(hostname=host).sign_in(request)

def sign_out(request, host):
    return GitHubAuth(hostname=host).sign_out(request)

def callback(request, host):
    return GitHubAuth(hostname=host).callback(request)
