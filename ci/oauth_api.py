
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

from django.shortcuts import redirect
from requests_oauthlib import OAuth2Session
from django.contrib import messages
import ci.models
import json
import logging

logger = logging.getLogger('ci')

class OAuthException(Exception):
    pass

def update_user_token(user, token):
    """
    Just saves a new token for a user.
    Outside the class for easier testing.
    """
    logger.info('Updating token for user "{}"'.format(user))
    user.token = json.dumps(token)
    user.save()

def update_session_token(session, oauth, token):
    """
    Just saves a new token for a user and update the session.
    Outside the class for easier testing.
    """
    user = ci.models.GitUser.objects.get(name=session[oauth._user_key], server__host_type=oauth._server_type)
    session[oauth._token_key] = token
    update_user_token(user, token)

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
            raise OAuthException("Git server %s (%s) is not configured" % (server, server.api_type()))
        self._prefix = "%s_" % self._config["hostname"]
        self._token_key = "%s_token" % self._prefix
        self._user_key = "%s_user" % self._prefix
        self._state_key = "%s_state" % self._prefix
        self._collaborators_key = "%s_collaborators" % self._prefix
        self._client_id = self._config.get("client_id", None)
        self._secret_id = self._config.get("secret_id", None)
        self._server_type = server.host_type
        self._api_url = None
        self._token_url = None
        self._auth_url = None
        self._user_url = None
        self._callback_user_key = None
        self._scope = None
        self._addition_keys = ["allowed_to_see_clients", "teams"]

    def start_session(self, session):
        """
        Starts a oauth session with the information stored in the browser session.
        The OAuth2Session will take care of most of the work. Just have to
        set a token_updater to update a token for BitBucket.
        Input:
          session: django.HttpRequest.session
        """
        if self._token_key in session:
            extra = {
                'client_id' : self._client_id,
                'client_secret' : self._secret_id,
                'auth' : (self._client_id, self._secret_id),
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
                user = ci.models.GitUser.objects.select_related('server').get(name=session[self._user_key], server=server)
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
            'client_id' : self._client_id,
            'client_secret' : self._secret_id,
            'auth' : (self._client_id, self._secret_id),
        }
        def token_updater(token):
            update_user_token(user, token)

        return OAuth2Session(
            self._client_id,
            token=token,
            auto_refresh_url=self._token_url,
            auto_refresh_kwargs=extra,
            token_updater=token_updater,
            )

    def set_browser_session_from_user(self, session, user):
        """
        This is purely for debugging purposes.
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
        Update the token for the user in the DB.
        """
        user = session[self._user_key]
        token = session[self._token_key]
        logger.info('Git user "%s" on %s logged in' % (user, self._config["hostname"]))
        server = ci.models.GitServer.objects.get(name=self._config["hostname"], host_type=self._server_type)
        gituser, created = ci.models.GitUser.objects.get_or_create(server=server, name=user)
        gituser.token = json.dumps(token)
        gituser.save()

    def get_json_value(self, response, name):
        """
        Helper function. Just gets a key value in the json response.
        """
        try:
            data = response.json()
        except Exception as e:
            raise OAuthException('Response did not contain JSON. Error : %s' % e.message)

        if name in data:
            return data[name]

        raise OAuthException('Could not find %s in json: %s' % (name, json.dumps(data, indent=2)))

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
                scope=self._scope)
        except Exception as e:
            raise OAuthException("You have not completed the authorization procedure. Please sign in. Error : %s" % e.message)

        try:
            # auth doesn't seem to be required for GitHub
            # but BitBucket seems to require basic authentication
            # with the client_id:secret
            token = oauth_session.fetch_token(
                self._token_url,
                client_secret=self._secret_id,
                authorization_response=request.build_absolute_uri(),
                auth=(self._client_id, self._secret_id),
                )
            request.session[self._token_key] = token
        except Exception as e:
            raise OAuthException("Failed to get authentication token : %s" % e.message)

    def callback(self, request):
        """
        This is the callback that will be called after the user
        authorizes.
        """
        try:
            self.fetch_token(request)
            if self._token_key in request.session:
                oauth_session = self.start_session(request.session)
                response = oauth_session.get(self._user_url)
                request.session[self._user_key] = self.get_json_value(response, self._callback_user_key)
                self.update_user(request.session)
                msg = '%s logged in on %s' % (request.session[self._user_key], self._config["hostname"])
                messages.info(request, msg)
                logger.info(msg)
            else:
                messages.error(request, "Couldn't get token when trying to log in")
        except Exception as e:
            msg = "Error when logging in : %s" % e.message
            logger.info(msg)
            messages.error(request, msg)
            self.sign_out(request)

        return self.do_redirect(request)

    def do_redirect(self, request):
        next_url = request.GET.get('next', None)
        if next_url is not None:
            return redirect(next_url)

        next_url = request.session.get('source_url')
        if next_url is not None:
            return redirect(next_url)

        return redirect('ci:main')

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
        request.session['source_url'] = request.GET.get('next', None)
        if token:
            messages.info(request, "Already signed in on %s" % self._config["hostname"])
            return self.do_redirect(request)

        oauth_session = OAuth2Session(self._client_id, scope=self._scope)
        authorization_url, state = oauth_session.authorization_url(self._auth_url)
        request.session[self._state_key] = state
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
            msg = 'Logged out "%s" on %s' % (user, self._config["hostname"])
            messages.info(request, msg)
            logger.info(msg)

        for key in request.session.keys():
            if key.startswith(self._prefix):
                request.session.pop(key, None)

        # Get rid of these keys on logout
        for key in self._addition_keys:
            request.session.pop(key, None)

        request.session.modified = True
        return self.do_redirect(request)
