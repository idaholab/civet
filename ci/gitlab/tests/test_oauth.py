from django.test import TestCase, RequestFactory, Client
from django.core.urlresolvers import reverse
from ci import gitlab
from ci.tests import utils
import requests
from mock import patch

class OAuthTestCase(TestCase):
  fixtures = ['base']
  def setUp(self):
    self.client = Client()
    self.factory = RequestFactory()

  class PostResponse(object):
    def __init__(self, data):
      self.data = data

    def json(self):
      return self.data

  @patch.object(requests, 'post')
  def test_sign_in(self, mock_post):
    url = reverse('ci:gitlab:sign_in')
    response = self.client.get(url)
    self.assertEqual(response.status_code, 200)

    # bad response
    username_data = {'username': 'testUser', 'password': 'testPassword' }
    mock_post.return_value = self.PostResponse({'error_description': 'none'})
    response = self.client.post(url, username_data)
    self.assertEqual(response.status_code, 200)

    username_data = {'username': 'testUser', 'password': 'testPassword' }
    response_data = {'private_token': '1234', 'username': 'testUser'}
    mock_post.return_value = self.PostResponse(response_data)
    response = self.client.post(url, username_data)
    self.assertEqual(response.status_code, 302)

  def test_sign_out(self):
    session = self.client.session
    session['gitlab_token'] = 'token'
    session['gitlab_state'] = 'state'
    session['gitlab_user'] = 'user'
    session.save()
    url = reverse('ci:gitlab:sign_out')
    response = self.client.get(url)
    self.assertEqual(response.status_code, 302) # redirect
    # make sure the session variables are gone
    self.assertNotIn('gitlab_token', self.client.session)
    self.assertNotIn('gitlab_state', self.client.session)
    self.assertNotIn('gitlab_user', self.client.session)

    data = {'source_url': reverse('ci:main')}
    response = self.client.get(url, data)
    self.assertEqual(response.status_code, 302) # redirect

  def test_session(self):
    user = utils.get_test_user()
    auth = gitlab.oauth.GitLabAuth()
    self.assertEqual(auth.start_session(self.client.session), None)

    session = self.client.session
    self.assertFalse(auth.is_signed_in(session))
    session['gitlab_user'] = 'no_user'
    session.save()
    self.assertFalse(auth.is_signed_in(session))
    session['gitlab_token'] = 'token'
    session.save()
    self.assertTrue(auth.is_signed_in(session))
    self.assertEqual(auth.signed_in_user(user.server, session), None)
    self.assertNotEqual(auth.start_session(session), None)

    session['gitlab_user'] = user.name
    session.save()
    self.assertEqual(auth.signed_in_user(user.server, session), user)
    self.assertNotEqual(auth.user_token_to_oauth_token(user), None)
    user2 = utils.create_user()
    self.assertEqual(auth.user_token_to_oauth_token(user2), None)

    self.assertNotEqual(auth.start_session_for_user(user), None)

    auth.set_browser_session_from_user(session, user)
    session.save()
    self.assertEqual(session['gitlab_user'], user.name)
