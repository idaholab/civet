
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
from django.urls import reverse

class GitLabAuth(OAuth):
    def __init__(self, hostname=None, server=None):
        super(GitLabAuth, self).__init__(hostname, settings.GITSERVER_GITLAB, server)
        self._api_url = '%s/api/v4' % self._config.get("api_url", "")
        self._html_url = self._config.get("html_url")
        self._token_url = '{}/oauth/token'.format(self._html_url)
        self._auth_url = '{}/oauth/authorize'.format(self._html_url)
        self._user_url = '{}/user'.format(self._api_url)
        self._callback_user_key = 'username'
        self._ssl_cert = self._config.get("ssl_cert", False)
        callback_url = reverse("ci:gitlab:callback", args=[self._config.get("hostname")])
        self._redirect_uri = "%s%s" % (self._config.get("civet_base_url", ""), callback_url)
        self._scope = ["api"]

def sign_in(request, host):
    return GitLabAuth(hostname=host).sign_in(request)

def sign_out(request, host):
    return GitLabAuth(hostname=host).sign_out(request)

def callback(request, host):
    return GitLabAuth(hostname=host).callback(request)
