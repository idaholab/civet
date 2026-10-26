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


class GitHubAuth(OAuth):
    def __init__(self, hostname=None, server=None):
        super(GitHubAuth, self).__init__(hostname, settings.GITSERVER_GITHUB, server)
        self._api_url = self._config.get("html_url", "")
        self._token_url = "%s/login/oauth/access_token" % self._api_url
        self._auth_url = "%s/login/oauth/authorize" % self._api_url
        self._user_url = "%s/user" % self._config.get("api_url", "")
        self._callback_user_key = "login"
        # Users signing in to view results only need to be identified
        # and have their organization and team memberships checked.
        # Which private repositories they can view is checked with
        # the token of a build user.
        self._scope = [
            "read:org",
        ]
        # Build users update statuses, comments, labels and merges
        # and check collaborators, which requires the repo scope
        self._build_scope = [
            "repo",
            "read:org",
        ]
        self._lists_private_repos = False
        callback_url = reverse(
            "ci:github:callback", args=[self._config.get("hostname")]
        )
        self._redirect_uri = "%s%s" % (
            self._config.get("civet_base_url", ""),
            callback_url,
        )

    def build_sign_in_url(self):
        return reverse("ci:github:sign_in_build", args=[self._config.get("hostname")])


def sign_in(request, host):
    return GitHubAuth(hostname=host).sign_in(request)


def sign_in_build(request, host):
    return GitHubAuth(hostname=host).sign_in(request, build=True)


def sign_out(request, host):
    return GitHubAuth(hostname=host).sign_out(request)


def callback(request, host):
    return GitHubAuth(hostname=host).callback(request)
