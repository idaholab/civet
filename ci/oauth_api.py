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
from django.conf import settings
from django.shortcuts import redirect
from django.utils.http import url_has_allowed_host_and_scheme
from requests_oauthlib import OAuth2Session
from oauthlib.oauth2.rfc6749.utils import scope_to_list
from django.contrib import messages
import ci.models
import json
import logging

logger = logging.getLogger("ci")


class OAuthException(Exception):
    pass


def token_has_scope(token, scope):
    """
    Whether the token was granted every scope in scope.
    A token that doesn't list its scope is assumed to have it.
    """
    if not scope or not token or not token.get("scope"):
        return True
    return set(scope_to_list(scope)).issubset(scope_to_list(token["scope"]))


def update_user_token(user, token, build_scope=None):
    """
    Saves a new token for a user. Only build users keep their token in
    the DB; the token of any other user is cleared instead, so the DB
    doesn't hold tokens for every user that has signed in.
    A build user's token is only saved if it has build_scope, so that a
    token with the narrower scope of ordinary users never replaces the
    token used to update the git server.
    Outside the class for easier testing.
    """
    if not user.needs_stored_token():
        user.token = ""
    elif not token_has_scope(token, build_scope):
        logger.info(
            'Not updating token for build user "{}"; it is missing scope "{}"'.format(
                user, " ".join(build_scope)
            )
        )
        return
    else:
        logger.info('Updating token for user "{}"'.format(user))
        user.token = json.dumps(token)
    user.save()


def update_session_token(session, oauth, token):
    """
    Just saves a new token for a user and update the session.
    Outside the class for easier testing.
    """
    user = ci.models.GitUser.objects.get(
        name=session[oauth._user_key], server__host_type=oauth._server_type
    )
    session[oauth._token_key] = token
    update_user_token(user, token, build_scope=oauth._build_scope)


class OAuth(object):
    """
    This is the base class for authenticating with OAuth2.
    Most methods won't work as is since they expect
    various self variables that are to be expected to
    be overridden in a derived class.
    """

    def __init__(self, hostname=None, host_type=None, server=None):
        if server is None:
            server = ci.models.GitServer.objects.get(name=hostname, host_type=host_type)
        self._config = server.server_config()
        if not self._config:
            raise OAuthException(
                "Git server %s (%s) is not configured" % (server, server.api_type())
            )
        self._hostname = self._config.get("hostname", "unknown_host")
        self._prefix = "%s_" % self._hostname
        self._token_key = "%s_token" % self._prefix
        self._user_key = "%s_user" % self._prefix
        self._state_key = "%s_state" % self._prefix
        self._scope_key = "%s_scope" % self._prefix
        # A build user that signed in and is being asked for the build scope
        self._pending_user_key = "%s_pending_user" % self._prefix
        self._collaborators_key = "%s_collaborators" % self._prefix
        self._write_access_key = "%s_write_access" % self._prefix
        self._client_id = self._config.get("client_id", None)
        self._secret_id = self._config.get("secret_id", None)
        self._server_type = server.host_type
        self._token_url = None
        self._auth_url = None
        self._user_url = None
        self._callback_user_key = None
        self._scope = None
        # The scope that build users need for their token in the DB, if
        # it is wider than _scope. Requested in callback() for build users.
        self._build_scope = None
        self._addition_keys = [
            "allowed_to_see_clients",
            "teams",
            "viewable_repos_timeout",
            "viewable_repos_cache",
        ]
        self._redirect_uri = None
        self._header = {
            "User-Agent": "INL-CIVET/1.0 (+https://github.com/idaholab/civet)"
        }

    def start_session(self, session):
        """
        Starts a oauth session with the information stored in the browser session.
        The OAuth2Session will take care of most of the work. Just have to
        set a token_updater to update the token when it is refreshed.
        Input:
          session: django.HttpRequest.session
        """
        if self._token_key in session:
            extra = {
                "client_id": self._client_id,
                "client_secret": self._secret_id,
                "auth": (self._client_id, self._secret_id),
            }

            def token_updater(token):
                update_session_token(session, self, token)

            return OAuth2Session(
                self._client_id,
                token=session[self._token_key],
                auto_refresh_url=self._token_url,
                auto_refresh_kwargs=extra,
                token_updater=token_updater,
            )
        return None

    def signed_in_user(self, server, session):
        """
        Checks the browser session for token server variables.
        If the token is there, the username should also be there.
        """
        if self._user_key in session and self._token_key in session:
            try:
                user = ci.models.GitUser.objects.select_related("server").get(
                    name=session[self._user_key], server=server
                )
                return user
            except ci.models.GitUser.DoesNotExist:
                pass
        return None

    def is_signed_in(self, session):
        """
        Checks the browser session for the required keys that
        relate to the username that is signed in.
        """
        if self._user_key not in session:
            return False

        if self._token_key not in session:
            return False

        return True

    def user_token_to_oauth_token(self, user):
        """
        We store the token information as json in the database.
        Convert it and return it.
        """
        if user.token:
            return json.loads(user.token)
        return None

    def start_session_for_user(self, user):
        """
        Grabs the token for the user in the DB, then
        starts a oauth session as that user.
        Input:
          user: models.GitUser: user to start the session for
        Return:
          OAuth2Session
        """
        token = self.user_token_to_oauth_token(user)
        extra = {
            "client_id": self._client_id,
            "client_secret": self._secret_id,
            "auth": (self._client_id, self._secret_id),
        }

        def token_updater(token):
            update_user_token(user, token, build_scope=self._build_scope)

        return OAuth2Session(
            self._client_id,
            token=token,
            auto_refresh_url=self._token_url,
            auto_refresh_kwargs=extra,
            token_updater=token_updater,
        )

    def set_browser_session_from_user(self, session, user):
        """
        This is purely for testing purposes.
        Allows to set browser session without actually
        having to login. So we don't have to have a
        public facing callback.
        """
        session[self._user_key] = user.name
        session[self._token_key] = self.user_token_to_oauth_token(user)
        # Get rid of these keys on login
        for key in self._addition_keys:
            session.pop(key, None)

    def update_user(self, session):
        """
        Update the token for the user in the DB if they are a build user.
        """
        user = session[self._user_key]
        token = session[self._token_key]
        logger.info('Git user "%s" on %s logged in' % (user, self._hostname))
        server = ci.models.GitServer.objects.get(
            name=self._hostname, host_type=self._server_type
        )
        gituser, created = ci.models.GitUser.objects.get_or_create(
            server=server, name=user
        )
        update_user_token(gituser, token, build_scope=self._build_scope)

    def needs_build_scope(self, username, token):
        """
        Whether the user is a build user that has to authorize the build
        scope: neither the token they signed in with nor the one stored
        for them has it.
        """
        if not self._build_scope or token_has_scope(token, self._build_scope):
            return False
        try:
            user = ci.models.GitUser.objects.get(
                name=username,
                server__name=self._hostname,
                server__host_type=self._server_type,
            )
        except ci.models.GitUser.DoesNotExist:
            return False
        if not user.needs_stored_token():
            return False
        stored = self.user_token_to_oauth_token(user)
        return not (stored and token_has_scope(stored, self._build_scope))

    def get_json_value(self, response, name):
        """
        Helper function. Just gets a key value in the json response.
        """
        try:
            data = response.json()
        except Exception as e:
            raise OAuthException("Response did not contain JSON. Error : %s" % e)

        if name in data:
            return data[name]

        raise OAuthException(
            "Could not find %s in json: %s" % (name, json.dumps(data, indent=2))
        )

    def fetch_token(self, request):
        """
        Get the actual token from the server.
        OAuth2Session takes care of everything, just
        add some error checking.
        """

        try:
            oauth_session = OAuth2Session(
                self._client_id,
                state=request.session[self._state_key],
                # Must match the scope sign_in() requested
                scope=request.session.get(self._scope_key, self._scope),
                redirect_uri=self._redirect_uri,
            )

        except Exception as e:
            raise OAuthException(
                "You have not completed the authorization procedure. Please sign in. Error : %s"
                % e
            )

        try:
            # auth doesn't seem to be required for GitHub
            # but some git servers require basic authentication
            # with the client_id:secret
            token = oauth_session.fetch_token(
                self._token_url,
                client_secret=self._secret_id,
                authorization_response=request.build_absolute_uri(),
                auth=(self._client_id, self._secret_id),
                headers=self._header,
            )
            request.session[self._token_key] = token
        except Exception as e:
            raise OAuthException("Failed to get authentication token : %s" % e)

    def callback(self, request):
        """
        This is the callback that will be called after the user
        authorizes.
        """
        try:
            self.fetch_token(request)
            if self._token_key in request.session:
                # Issue a new session key on login so that a session id
                # planted before sign in doesn't become authenticated
                request.session.cycle_key()
                # Restore the default expiry set aside by sign_in()
                request.session.set_expiry(None)
                oauth_session = self.start_session(request.session)
                response = oauth_session.get(self._user_url, headers=self._header)
                response.raise_for_status()
                username = self.get_json_value(response, self._callback_user_key)
                pending = request.session.pop(self._pending_user_key, None)
                if pending is not None and username != pending:
                    raise OAuthException(
                        'Authorized as "%s" instead of "%s"' % (username, pending)
                    )
                token = request.session[self._token_key]
                if pending is None and self.needs_build_scope(username, token):
                    # Build users need the build scope to update the git
                    # server, so ask for it before signing them in
                    logger.info(
                        'Requesting scope "%s" for build user "%s" on %s'
                        % (" ".join(self._build_scope), username, self._hostname)
                    )
                    request.session.pop(self._token_key)
                    request.session[self._pending_user_key] = username
                    return self.authorize(request, self._build_scope)
                request.session[self._user_key] = username
                self.update_user(request.session)
                msg = "%s logged in on %s" % (username, self._hostname)
                messages.info(request, msg)
                logger.info(msg)
            else:
                messages.error(request, "Couldn't get token when trying to log in")
        except Exception as e:
            msg = "Error when logging in : %s" % e
            logger.info(msg)
            messages.error(request, msg)
            self.sign_out(request)

        return self.do_redirect(request)

    def _safe_redirect_url(self, request, next_url, fallback="ci:main"):
        """
        Return next_url only if it is safe to redirect to (same host/scheme).
        Falls back to fallback if next_url is missing or points off-site.
        """
        if next_url and url_has_allowed_host_and_scheme(
            next_url,
            allowed_hosts={request.get_host()},
            require_https=request.is_secure(),
        ):
            return next_url
        return fallback

    def do_redirect(self, request):
        next_url = request.GET.get("next")
        if not next_url:
            next_url = request.session.get("source_url")

        return redirect(self._safe_redirect_url(request, next_url))

    def sign_in(self, request):
        """
        Endpoint for the user signing in. Will start
        the OAuth2 authentication process.
        After this step the user will be redirected
        to the server sign in page. After that, the server
        will automatically call our registered callback,
        which is "callback" above.
        That will get access to the token that will be
        used in all future communications.
        """
        token = request.session.get(self._token_key)
        request.session["source_url"] = request.GET.get("next", None)
        if token:
            messages.info(request, "Already signed in on %s" % self._hostname)
            return self.do_redirect(request)
        # Start over if a request for the build scope wasn't finished
        request.session.pop(self._pending_user_key, None)
        return self.authorize(request, self._scope)

    def authorize(self, request, scope):
        """
        Redirect to the server to authorize scope; the server then
        calls callback().
        """
        oauth_session = OAuth2Session(
            self._client_id, scope=scope, redirect_uri=self._redirect_uri
        )
        authorization_url, state = oauth_session.authorization_url(self._auth_url)
        request.session[self._state_key] = state
        request.session[self._scope_key] = scope
        # Crawlers follow the sign in link without ever finishing the
        # authorization, so expire the session quickly unless the
        # callback completes the sign in.
        request.session.set_expiry(settings.SIGN_IN_SESSION_EXPIRY)
        # Get rid of these keys on login
        for key in self._addition_keys:
            request.session.pop(key, None)
        return redirect(authorization_url)

    def sign_out(self, request):
        """
        Just removes all the server specific
        entries in the user's session.
        """
        user = request.session.get(self._user_key, None)
        if user:
            msg = 'Logged out "%s" on %s' % (user, self._hostname)
            messages.info(request, msg)
            logger.info(msg)

        for key in list(request.session.keys()):
            if key.startswith(self._prefix):
                request.session.pop(key, None)

        # Get rid of these keys on logout
        for key in self._addition_keys:
            request.session.pop(key, None)

        request.session.modified = True
        return self.do_redirect(request)
