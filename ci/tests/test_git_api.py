from django.test import TestCase
from ci.git_api import GitAPI
class GitAPITestCase(TestCase):
  """
  this class is just a base class for the actual git servers.
  doesn't do anything for now.
  just call the methods for coverage purposes
  """
  def test_api(self):
    gapi = GitAPI()
    gapi.sign_in_url()
    gapi.repo_url('owner', 'repo')
    gapi.commit_html_url('owner', 'repo', 'sha')
    gapi.get_repos('auth_session', 'session')
    gapi.get_branches('auth_session', 'owner', 'repo')
    gapi.update_pr_status('auth_session', 'base', 'head', 'state', 'event_url', 'desc', 'context')
    gapi.is_collaborator('auth_session', 'user', 'repo')
    gapi.pr_comment('auth_session', 'url', 'msg')
    gapi.last_sha('auth_session', 'owner', 'repo', 'branch')
    gapi.install_webhooks('request', 'auth_session', 'user', 'repo')
