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
from ci.oauth_api import OAuth
from django.conf import settings
from django.urls import reverse
import logging
import requests

logger = logging.getLogger("ci")


class GitHubAuth(OAuth):
    def __init__(self, hostname=None, server=None):
        super(GitHubAuth, self).__init__(hostname, settings.GITSERVER_GITHUB, server)
        self._api_url = self._config.get("html_url", "")
        self._token_url = "%s/login/oauth/access_token" % self._api_url
        self._auth_url = "%s/login/oauth/authorize" % self._api_url
        self._user_url = "%s/user" % self._config.get("api_url", "")
        self._callback_user_key = "login"
        # Signed in users are only identified; CIVET checks their access
        # with the build user's token
        self._scope = []
        # Build users update statuses, comments, labels and issues, and
        # check org membership, including private memberships
        self._build_scope = ["repo", "read:org"]
        callback_url = reverse(
            "ci:github:callback", args=[self._config.get("hostname")]
        )
        self._redirect_uri = "%s%s" % (
            self._config.get("civet_base_url", ""),
            callback_url,
        )

    def revoke_grant(self, token):
        """
        GitHub returns every scope the user authorized before, so to drop
        a scope the grant itself has to be revoked.
        """
        api_url = self._config.get("api_url", "")
        ssl_cert = self._config.get("ssl_cert", True)
        try:
            response = requests.delete(
                "%s/applications/%s/grant" % (api_url, self._client_id),
                auth=(self._client_id, self._secret_id),
                json={"access_token": token.get("access_token")},
                headers=self._header,
                timeout=self._config.get("request_timeout", 5),
                verify=ssl_cert if isinstance(ssl_cert, str) and ssl_cert else True,
            )
        except Exception as e:
            logger.warning("Failed to revoke grant on %s: %s" % (self._hostname, e))
            return False
        if response.status_code != 204:
            logger.warning(
                "Failed to revoke grant on %s: status %s"
                % (self._hostname, response.status_code)
            )
            return False
        return True


def sign_in(request, host):
    return GitHubAuth(hostname=host).sign_in(request)


def sign_out(request, host):
    return GitHubAuth(hostname=host).sign_out(request)


def callback(request, host):
    return GitHubAuth(hostname=host).callback(request)
