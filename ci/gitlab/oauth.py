from django.conf import settings
from django.shortcuts import render, redirect
from django import forms
from ci.oauth import OAuth
import requests
from django.contrib import messages

class GitLabAuth(OAuth):
  def __init__(self):
    self._prefix = 'gitlab_'
    self._token_key = 'gitlab_token'
    self._user_key = 'gitlab_user'
    self._state_key = 'gitlab_state' # not used
    self._client_id = None
    self._secret_id = None
    self._server_type = settings.GITSERVER_GITLAB
    self._api_url = settings.GITLAB_API_URL
    #self._token_url = '{}/oauth/token'.format(self._api_url)
    self._token_url = '{}/api/v3/session'.format(self._api_url)
    self._auth_url = '{}/oauth/authorize'.format(self._api_url)
    self._user_url = '{}/user'.format(self._api_url)
    self._callback_user_key = 'username'
    self._scope = ''


class SignInForm(forms.Form):
  username = forms.CharField(label='Username', max_length=120)
  password = forms.CharField(label='Password', max_length=120, widget=forms.PasswordInput)

  def clean(self):
    """
    This is the validation that the username and password
    will give us a valid access token.
    """
    cleaned_data = super(SignInForm, self).clean()
    if 'username' not in cleaned_data or 'password' not in cleaned_data:
      raise forms.ValidationError('Invalid username or password')
    username = cleaned_data['username']
    password = cleaned_data['password']
    user_data = {'login': username, 'password': password}
    url = GitLabAuth()._token_url
    response = requests.post(url, params=user_data, verify=False).json()
    if 'username' not in response:
      del self.cleaned_data['password']
      raise forms.ValidationError('Invalid username or password. Response: %s' % response)

    self.token = response['private_token']

def sign_in(request):
  if request.method == 'POST':
    form = SignInForm(request.POST)
    if form.is_valid():
      auth = GitLabAuth()
      request.session[auth._user_key] = form.cleaned_data['username']
      token = {'access_token': form.token}
      request.session[auth._token_key] = token
      auth.update_user(request.session)
      source_url = request.session.get('source_url', None)
      messages.info(request, 'Logged into GitLab as {}'.format(form.cleaned_data['username']))
      if source_url:
        return redirect(source_url)
      else:
        return redirect('ci:main')
  else:
    form = SignInForm()
    request.session['source_url'] = request.GET.get('next', None)

  return render(request, 'ci/gitlab_sign_in.html', {'form': form})

def sign_out(request):
  return GitLabAuth().sign_out(request)
