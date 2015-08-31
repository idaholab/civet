from django.core.urlresolvers import reverse
from django.conf import settings
import logging, traceback
import json
import urllib, requests

logger = logging.getLogger('ci')

class GitLabException(Exception):
  pass

class GitLabAPI(object):
  _api_url = '{}/api/v3'.format(settings.GITLAB_API_URL)
  _html_url = settings.GITLAB_API_URL
  # these aren't used. Only for compatibility with
  # the GitHub API
  PENDING = 0
  ERROR = 1
  SUCCESS = 2
  FAILURE = 3

  def post(self, url, token, data):
    params = {'private_token': token}
    return requests.post(url, params=params, data=data, verify=False)

  def get(self, url, token, extra_args={}):
    extra_args['private_token'] = token
    extra_args['per_page'] = 100
    logger.debug('Getting url {} with token = {}'.format(url, token))
    return requests.get(url, params=extra_args, verify=False)

  def sign_in_url(self):
    return reverse('ci:gitlab:sign_in')

  def users_url(self):
    return "%s/users" % self._api_url

  def repos_url(self):
    return "%s/projects/owned" % self._api_url

  def orgs_url(self):
    return "%s/user/orgs" % self._api_url

  def projects_url(self):
    return "%s/projects/" % (self._api_url)

  def repo_url(self, owner, repo):
    name = '{}/{}'.format(owner, repo)
    return '{}/{}'.format(self.projects_url(), urllib.quote_plus(name))

  def branches_url(self, owner, repo):
    return "%s/repository/branches" % (self.repo_url(owner, repo))

  def branch_by_id_url(self, repo_id, branch_id):
    return "%s/%s/repository/branches/%s" % (self.projects_url(), repo_id, branch_id)

  def branch_url(self, owner, repo, branch):
    return "%s/%s" % (self.branches_url(owner, repo), branch)

  def repo_html_url(self, owner, repo):
    return '{}/{}/{}'.format(self._html_url, owner, repo)

  def comment_html_url(self, project_id, pr_id):
    return '{}/projects/{}/merge_request/{}/comments'.format(self._html_url, project_id, pr_id)

  def commit_html_url(self, owner, repo, sha):
    return '{}/commit/{}'.format(self.repo_html_url(owner, repo), sha)

  def pr_html_url(self, repo_path, pr_iid):
    return '{}/{}/merge_requests/{}'.format(self._html_url, repo_path, pr_iid)

  def members_url(self, owner, repo):
    return "%s/members" % (self.repo_url(owner, repo))

  def groups_url(self):
    return "%s/groups" % (self._api_url)

  def group_members_url(self, group_id):
    return "%s/%s/members" % (self.groups_url(), group_id)

  def get_token(self, auth_session):
    return auth_session.token['access_token']

  def get_repos(self, auth_session, session):
    if 'gitlab_repos' in session:
      return session['gitlab_repos']

    token = self.get_token(auth_session)
    response = self.get(self.repos_url(), token)
    data = self.get_all_pages(auth_session, response)
    owner_repo = []
    for repo in data:
      if repo['namespace']['name'] == session['gitlab_user']:
        owner_repo.append(repo['name'])
    session['gitlab_repos'] = owner_repo
    return owner_repo

  def get_branches(self, auth_session, owner, repo):
    token = self.get_token(auth_session)
    response = self.get(self.branches_url(owner, repo), token)
    data = self.get_all_pages(auth_session, response)
    branches = []
    for branch in data:
      branches.append(branch['name'])
    return branches

  def get_org_repos(self, auth_session, session):
    if 'gitlab_org_repos' in session:
      return session['gitlab_org_repos']

    token = self.get_token(auth_session)
    response = self.get(self.projects_url(), token)
    data = self.get_all_pages(auth_session, response)
    org_repo = []
    user = session['gitlab_user']
    for repo in data:
      org = repo['namespace']['name']
      if org != user:
        org_repo.append('{}/{}'.format(org, repo['name']))
    session['gitlab_org_repos'] = org_repo
    return org_repo

  def update_pr_status(self, oauth_session, base, head, state, event_url, description, context):
    """
    This doesn't work on GitLab.
    """
    pass

  def is_collaborator(self, oauth_session, user, repo):
    # first just check to see if the user is the owner
    if repo.user == user:
      return True
    # now ask gitlab
    url = self.members_url(repo.user.name, repo.name)
    token = self.get_token(oauth_session)
    response = self.get(url, token)
    data = self.get_all_pages(oauth_session, response)
    for member in data:
      if member.get('username') == user.name:
        return True

    response = self.get(self.groups_url(), token)
    data = self.get_all_pages(oauth_session, response)
    group_id = None
    for group in data:
      if group.get('name') == repo.user.name:
        group_id = group['id']
        break
    response = self.get(self.group_members_url(group_id), token)
    data = self.get_all_pages(oauth_session, response)
    for member in data:
      if member.get('username') == user.name:
        return True
    return False

  def pr_comment(self, oauth_session, url, msg):
    if settings.NO_REMOTE_UPDATE:
      return

    comment = {'note': msg}
    try:
      token = self.get_token(oauth_session)
      self.post(url, token, data=json.dumps(comment))
    except Exception as e:
      logger.warning("Failed to leave comment.\nComment: %s\nError: %s" %(msg, traceback.format_exc(e)))

  def last_sha(self, oauth_session, owner, repo, branch):
    url = self.branch_url(owner, repo, branch)
    try:
      token = self.get_token(oauth_session)
      response = self.get(url, token)
      if 'commit' in response.content:
        data = json.loads(response.content)
        return data['commit']['id']
      logger.warning("Unknown branch information for %s\nResponse: %s" % (url, response.content))
    except Exception as e:
      logger.warning("Failed to get branch information at %s.\nError: %s" % (url, traceback.format_exc(e)))
    return None

  def get_all_pages(self, oauth_session, response):
    all_json = response.json()
    token = self.get_token(oauth_session)
    while 'next' in response.links:
      response = self.get(response.links['next']['url'], token)
      all_json.extends(response.json())
    return all_json

  def install_webhooks(self, request, auth_session, user, repo):
    hook_url = '%s/hooks' % self.repo_url(repo.user.name, repo.name)
    callback_url = request.build_absolute_uri(reverse('ci:gitlab:webhook', args=[user.build_key]))
    token = self.get_token(auth_session)
    response = self.get(hook_url, token)
    data = self.get_all_pages(auth_session, response)
    have_hook = False
    for hook in data:
      logger.debug('data : {}'.format(data))
      if hook.get('merge_requests_events') and hook.get('push_events') and hook.get('url') == callback_url:
        have_hook = True
        break

    if have_hook:
      return None

    add_hook = {
        'url': callback_url,
        'push_events': 'true',
        'merge_requests_events': 'true',
        'issue_events': 'false',
        }
    response = self.post(hook_url, token, add_hook)
    if response.status_code >= 400:
      raise GitLabException(response.json())
    logger.debug('Added webhook to %s for user %s' % (repo, user.name))
