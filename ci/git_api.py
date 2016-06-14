class GitException(Exception):
  pass

class GitAPI(object):
  _api_url = None
  _github_url = None
  PENDING = 0
  ERROR = 1
  SUCCESS = 2
  FAILURE = 3
  RUNNING = 4
  CANCELED = 5

  def sign_in_url(self):
    pass

  def git_url(self, owner, repo):
    pass

  def repo_url(self, owner, repo):
    pass

  def get_repos(self, auth_session, session):
    pass

  def get_branches(self, auth_session, owner, repo):
    pass

  def update_pr_status(self, oauth_session, base, head, state, event_url, description, context):
    pass

  def is_collaborator(self, oauth_session, user, repo):
    pass

  def pr_comment(self, oauth_session, url, msg):
    pass

  def last_sha(self, oauth_session, owner, repo, branch):
    pass

  def install_webhooks(self, request, auth_session, user, repo):
    """
    Updates the webhook for this server on GitHub.
    Input:
      auth_session: requests_oauthlib.OAuth2Session for the user updating the web hooks.
      user: models.GitUser of the user trying to update the web hooks.
      repo: models.Repository of the repository to set the web hook on.
    Raises:
      GitException if there are any errors.
    """
    pass

  def pr_html_url(self, owner, repo, pr_num):
    pass

  def repo_html_url(self, owner, repo):
    pass

  def branch_html_url(self, owner, repo, branch):
    pass

  def commit_html_url(self, owner, repo, sha):
    pass


