from django.core.urlresolvers import reverse
import logging
import json
#from django.conf import settings

logger = logging.getLogger('ci')

class BitBucketException(Exception):
  pass

class BitBucketAPI(object):
  _api2_url = 'https://api.bitbucket.org/2.0'
  _api1_url = 'https://bitbucket.org/api/1.0'
  _bitbucket_url = 'https://bitbucket.org'
  PENDING = 0
  ERROR = 1
  SUCCESS = 2
  FAILURE = 3
  STATUS = ((PENDING, "pending"),
      (ERROR, "error"),
      (SUCCESS, "success"),
      (FAILURE, "failure"),
      )

  def sign_in_url(self):
    return reverse('ci:bitbucket:sign_in')

  def user_url(self):
    return "%s/user" % self._api1_url

  def repos_url(self, affiliation=None):
    return '{}/user/repositories'.format(self._api1_url)

  def repo_url(self, owner, repo):
    return "%s/repositories/%s/%s" % (self._api1_url, owner, repo)

  def branches_url(self, owner, repo):
    return "%s/branches" % (self.repo_url(owner, repo))

  def repo_html_url(self, owner, repo):
    return "%s/%s/%s" %(self._bitbucket_url, owner, repo)

  def commit_html_url(self, owner, repo, sha):
    return "%s/commits/%s" % (self.repo_html_url(owner, repo), sha)

  def commit_comment_url(self, owner, repo, sha):
    return self.commit_html_url(owner, repo, sha)

  def collaborator_url(self, owner):
    return "%s/repositories/%s" % (self._api2_url, owner)

  def get_repos(self, auth_session, session):
    if 'bitbucket_repos' in session and 'bitbucket_org_repos' in session:
      return session['bitbucket_repos']

    response = auth_session.get(self.repos_url())
    data = self.get_all_pages(auth_session, response)
    owner_repo = []
    org_repos = []
    user = session['bitbucket_user']
    if 'message' not in data:
      for repo in data:
        owner = repo['owner']
        name = repo['name']
        if owner == user:
          owner_repo.append(name)
        else:
          org_repos.append('{}/{}'.format(owner, name))
    logger.debug('Org repos: {}'.format(org_repos))
    logger.debug('Repos repos: {}'.format(owner_repo))
    session['bitbucket_org_repos'] = org_repos
    session['bitbucket_repos'] = owner_repo
    return owner_repo

  def get_branches(self, auth_session, owner, repo):
    response = auth_session.get(self.branches_url(owner, repo))
    data = self.get_all_pages(auth_session, response)
    if response.status_code == 200:
      return data.keys()
    return []

  def get_org_repos(self, auth_session, session):
    if 'bitbucket_org_repos' in session:
      return session['bitbucket_org_repos']
    self.get_repos(auth_session, session)
    return session['bitbucket_org_repos']

  def update_pr_status(self, oauth_session, base, head, state, event_url, description, context):
    """
    Not supported on BitBucket
    """
    pass

  def is_collaborator(self, oauth_session, user, repo):
    # first just check to see if the user is the owner
    if repo.user == user:
      return True
    # now ask bitbucket
    url = self.collaborator_url(repo.user.name)
    logger.debug('Checking %s' % url)
    response = oauth_session.get(url, data={'role': 'contributor'})
    data = self.get_all_pages(oauth_session, response)
    if response.status_code == 200:
      for repo_data in data['values']:
        if repo_data['name'] == repo.name:
          logger.debug('User %s is a collaborator on %s' % (user, repo))
          return True
    logger.debug('User %s is not a collaborator on %s' % (user, repo))
    return False

  def pr_comment(self, oauth_session, url, msg):
    """
    Doesn't seem to be able to comment on PRs.
    """
    pass

  def get_all_pages(self, oauth_session, response):
    all_json = response.json()
    while 'next' in response.links:
      response = oauth_session.get(response.links['next']['url'])
      all_json.extends(response.json())
    return all_json

  def install_webhooks(self, request, auth_session, user, repo):

    hook_url = '{}/repositories/{}/{}/hooks'.format(self._api2_url, repo.user.name, repo.name)
    callback_url = request.build_absolute_uri(reverse('ci:bitbucket:webhook', args=[user.build_key]))
    response = auth_session.get(hook_url)
    data = self.get_all_pages(auth_session, response)
    have_hook = False
    for hook in data['values']:
      if 'pullrequest:created' not in hook['events'] or 'repo:push' not in hook['events']:
        continue
      if hook['url'] == callback_url:
        have_hook = True
        break

    if have_hook:
      logger.debug('Webhook already exists')
      return None

    add_hook = {
        'description': 'CIVET webook',
        'url': callback_url,
        'active': True,
        'events': [
            'repo:push',
            'pullrequest:created',
            'pullrequest:updated',
            'pullrequest:approved',
            'pullrequest:rejected',
            'pullrequest:fulfilled',
            ],
        }
    response = auth_session.post(hook_url, data=json.dumps(add_hook))
    data = response.json()
    if response.status_code != 201:
      logger.debug('data: {}'.format(json.dumps(data, indent=4)))
      raise BitBucketException(data)
    logger.debug('Added webhook to %s for user %s' % (repo, user.name))
