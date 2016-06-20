import abc

class GitException(Exception):
  pass

class GitAPI(object):
  __metaclass__ = abc.ABCMeta
  _api_url = None
  _github_url = None
  PENDING = 0
  ERROR = 1
  SUCCESS = 2
  FAILURE = 3
  RUNNING = 4
  CANCELED = 5

  @abc.abstractmethod
  def sign_in_url(self):
    pass

  @abc.abstractmethod
  def git_url(self, owner, repo):
    """
    Git path to the repository. Ex, git@github.com/idaholab/civet
    Input:
      owner: str: Owner of the repository
      repo: str: Name of the repository
    """
    pass

  @abc.abstractmethod
  def repo_url(self, owner, repo):
    pass

  @abc.abstractmethod
  def get_repos(self, auth_session, session):
    pass

  @abc.abstractmethod
  def get_branches(self, auth_session, owner, repo):
    pass

  @abc.abstractmethod
  def update_pr_status(self, oauth_session, base, head, state, event_url, description, context):
    pass

  @abc.abstractmethod
  def is_collaborator(self, oauth_session, user, repo):
    pass

  @abc.abstractmethod
  def pr_comment(self, oauth_session, url, msg):
    pass

  @abc.abstractmethod
  def last_sha(self, oauth_session, owner, repo, branch):
    pass

  @abc.abstractmethod
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

  @abc.abstractmethod
  def pr_html_url(self, owner, repo, pr_num):
    """
    Gets a URL to the pull request.
    Input:
      owner: str: Owner of the repo
      repo: str: Name of the repo
      pr_num: int: Pull request number
    Return:
      str: URL on the gitserver to the PR
    """

  @abc.abstractmethod
  def repo_html_url(self, owner, repo):
    """
    Gets a URL to the repository
    Input:
      owner: str: Owner of the repo
      repo: str: Name of the repo
    Return:
      str: URL on the gitserver to the repo
    """
    pass

  @abc.abstractmethod
  def branch_html_url(self, owner, repo, branch):
    """
    Gets a URL to the branch
    Input:
      owner: str: Owner of the repo
      repo: str: Name of the repo
      branch: str: Name of the branch
    Return:
      str: URL on the gitserver to the branch
    """
    pass

  @abc.abstractmethod
  def commit_html_url(self, owner, repo, sha):
    """
    Gets a URL to a commit
    Input:
      owner: str: Owner of the repo
      repo: str: Name of the repo
      sha: str: SHA of on the repo
    Return:
      str: URL on the gitserver to the commit
    """
    pass
