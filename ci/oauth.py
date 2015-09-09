from django.shortcuts import redirect
from requests_oauthlib import OAuth2Session
from django.contrib import messages
import ci.models
import json
import logging

logger = logging.getLogger('ci')

class OAuthException(Exception):
  pass

class OAuth(object):
  def start_session(self, session):
    if self._token_key in session:
      extra = {
          'client_id' : self._client_id,
          'client_secret' : self._secret_id,
          'auth' : (self._client_id, self._secret_id),
      }
      def token_updater(token):
        user = ci.models.GitUser.objects.get(name=session[self._user_key], server__host_type=self._server_type)
        logger.debug('Updating token for user {}'.format(user))
        session[self._token_key] = token
        user.token = json.dumps(token)
        user.save()


      return OAuth2Session(
          self._client_id,
          token=session[self._token_key],
          auto_refresh_url=self._token_url,
          auto_refresh_kwargs=extra,
          token_updater=token_updater,
          )
    return None

  def signed_in_user(self, server, session):
    if self._user_key in session and self._token_key in session:
      try:
        user = ci.models.GitUser.objects.get(name=session[self._user_key], server=server)
        return user
      except ci.models.GitUser.DoesNotExist:
        pass
    return None

  def is_signed_in(self, session):
    if self._user_key not in session:
      return False

    if self._token_key not in session:
      return False

    return True

  def user_token_to_oauth_token(self, user):
    if user.token:
      return json.loads(user.token)
    return None

  def start_session_for_user(self, user):
    token = self.user_token_to_oauth_token(user)
    extra = {
        'client_id' : self._client_id,
        'client_secret' : self._secret_id,
        'auth' : (self._client_id, self._secret_id),
    }
    def token_updater(token):
      user.token = json.dumps(token)
      user.save()

    return OAuth2Session(
        self._client_id,
        token=token,
        auto_refresh_url=self._token_url,
        auto_refresh_kwargs=extra,
        token_updater=token_updater,
        )
    return OAuth2Session(self._client_id, token=token, auto_refresh_url=self._token_url)

  def set_browser_session_from_user(self, session, user):
    """
    This is purely for debugging purposes.
    Allows to set browser session without actually
    having to login. So we don't have to have a
    public facing callback.
    """
    session[self._user_key] = user.name
    session[self._token_key] = self.user_token_to_oauth_token(user)

  def update_user(self, session):
    """
    Update the token for the user in the DB.
    """
    user = session[self._user_key]
    token = session[self._token_key]
    logger.info('Git user "{}" logged in'.format(user))
    #update the DB
    server = ci.models.GitServer.objects.get(host_type=self._server_type)
    gituser, created = ci.models.GitUser.objects.get_or_create(server=server, name=user)
    gituser.token = json.dumps(token)
    gituser.save()

  def get_json_value(self, response, name):
    try:
      data = response.json()
    except Exception as e:
      raise OAuthException('Response did not contain JSON. Error : %s' % e.message)

    if name in data:
      return data[name]

    raise OAuthException('Could not find %s in json' % name)

  def fetch_token(self, request):
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
        messages.info(request, '{} logged in'.format(request.session[self._user_key]))
      else:
        messages.info(request, "Couldn't get token when trying to log in")
    except Exception as e:
      messages.info(request, "Error when logging in : %s" % e.message)
      self.sign_out(request)

    source_url = request.session.get('source_url', None)
    if source_url:
      return redirect(source_url)
    else:
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
      messages.info(request, "Already signed in")
      if request.session['source_url']:
        redirect(request.session['source_url'])
      else:
        redirect('ci:main')

    oauth_session = OAuth2Session(self._client_id, scope=self._scope)
    authorization_url, state = oauth_session.authorization_url(self._auth_url)
    request.session[self._state_key] = state
    return redirect(authorization_url)

  def sign_out(self, request):
    """
    Just removes all the server specific
    entries in the user's session.
    """
    user = request.session.get(self._user_key, None)
    if user:
      messages.info(request, 'Logged out {}'.format(user))

    for key in request.session.keys():
      if key.startswith(self._prefix):
        request.session.pop(key, None)

    source_url = request.session.get('source_url', None)
    if source_url:
      return redirect(source_url)
    else:
      return redirect('ci:main')
