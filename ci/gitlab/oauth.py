
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

from django.shortcuts import render, redirect
from django import forms
from ci.oauth_api import OAuth
import requests
from django.contrib import messages
from django.conf import settings

class GitLabAuth(OAuth):
    def __init__(self, hostname=None, host_type=None, server=None):
        super(GitLabAuth, self).__init__(hostname, host_type, server)
        self._client_id = None
        self._secret_id = None
        self._api_url = self._config.get("api_url")
        self._token_url = '{}/api/v4/session'.format(self._api_url)
        self._auth_url = '{}/oauth/authorize'.format(self._api_url)
        self._user_url = '{}/user'.format(self._api_url)
        self._callback_user_key = 'username'
        self._ssl_cert = self._config.get("ssl_cert", False)
        self._scope = ''


class SignInForm(forms.Form):
    username = forms.CharField(label='Username', max_length=120)
    password = forms.CharField(label='Password', max_length=120, widget=forms.PasswordInput)

    def __init__(self, post=None, token_url="", host="", ssl_cert=None):
        super(SignInForm, self).__init__(post)
        self._token_url = token_url
        self.host = host
        self._ssl_cert = ssl_cert

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
        response = requests.post(self._token_url, params=user_data, verify=self._ssl_cert).json()
        if 'username' not in response:
            del self.cleaned_data['password']
            raise forms.ValidationError('Invalid username or password. Response: %s' % response)

        self.token = response['private_token']

def sign_in(request, host):
    auth = GitLabAuth(hostname=host, host_type=settings.GITSERVER_GITLAB)
    for key in auth._addition_keys:
        request.session.pop(key, None)

    if request.method == 'POST':
        form = SignInForm(request.POST, auth._token_url, host, auth._ssl_cert)
        if form.is_valid():
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
        form = SignInForm(token_url=auth._token_url, host=host, ssl_cert=auth._ssl_cert)
        request.session['source_url'] = request.GET.get('next', None)

    return render(request, 'ci/gitlab_sign_in.html', {'form': form})

def sign_out(request, host):
    return GitLabAuth(hostname=host, host_type=settings.GITSERVER_GITLAB).sign_out(request)
