from django.shortcuts import redirect
from requests_oauthlib import OAuth2Session
from django.contrib import messages
from ci import models
import logging

logger = logging.getLogger('ci')

class OAuthException(Exception):
  pass

class OAuth(object):
  def start_session(self, session):
    if self._token_key in session:
      return OAuth2Session(self._client_id, token=session[self._token_key])
    return None

  def signed_in_user(self, server, session):
    if self._user_key in session and self._token_key in session:
      try:
        user = models.GitUser.objects.get(name=session[self._user_key], server=server)
        return user
      except models.GitUser.DoesNotExist:
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
      token = { 'access_token': user.token.token,
        'token_type': user.token.token_type,
        'scope': [user.token.token_scope],
        }
      return token
    return None

  def start_session_for_user(self, user):
    token = self.user_token_to_oauth_token(user)
    return OAuth2Session(self._user_key, token=token)

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
    server = models.GitServer.objects.get(host_type=self._server_type)
    gituser, created = models.GitUser.objects.get_or_create(server=server, name=user)
    if not gituser.token:
      gituser.token = models.OAuthToken.objects.create(
          token=token['access_token'],
          token_type=token['token_type'],
          token_scope=token['scope'],
          )
    else:
      gituser.token.token = token['access_token']
      gituser.token.token_type = token['token_type']
      gituser.token.token_scope = token['scope']

    gituser.token.save()
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
      token = oauth_session.fetch_token(
          self._token_url,
          client_secret=self._secret_id,
          authorization_response=request.build_absolute_uri(),
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
        messages.info(request, "Error when logging in : Couldn't get token.")
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
