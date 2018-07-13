
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
from ci.oauth_api import OAuth
from django.conf import settings
from django.core.urlresolvers import reverse

class BitBucketAuth(OAuth):
    """
    OAuth2 with BitBucket.
    Some changes to the base OAuth implementation were required.
    BitBucket requires user/password authentication ( which are the client/secret ).
    Tokens are set to expire after an hour so the refresh token mechanisms needed
    to be put in place.
    These changes don't seem to affect GitHub.
    """
    def __init__(self, hostname=None, server=None):
        super(BitBucketAuth, self).__init__(hostname, settings.GITSERVER_BITBUCKET, server)
        self._api_url = self._config.get("html_url", "")
        self._token_url = '{}/site/oauth2/access_token'.format(self._api_url)
        self._auth_url = '{}/site/oauth2/authorize'.format(self._api_url)
        self._user_url = "%s/user" % self._config.get("api2_url", "")
        self._callback_user_key = 'username'
        callback_url = reverse("ci:bitbucket:callback", args=[self._config.get("hostname")])
        self._redirect_uri = "%s%s" % (self._config.get("civet_base_url", ""), callback_url)
        self._scope = None

def sign_in(request, host):
    return BitBucketAuth(hostname=host).sign_in(request)

def sign_out(request, host):
    return BitBucketAuth(hostname=host).sign_out(request)

def callback(request, host):
    return BitBucketAuth(hostname=host).callback(request)
