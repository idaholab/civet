
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

from django.core.urlresolvers import reverse
import logging, traceback
import json
from ci.git_api import GitAPI, GitException
from oauth import GitHubAuth
from django.conf import settings

logger = logging.getLogger('ci')

class GitHubAPI(GitAPI):
    _api_url = 'https://api.github.com'
    _github_url = 'https://github.com'
    STATUS = ((GitAPI.PENDING, "pending"),
        (GitAPI.ERROR, "error"),
        (GitAPI.SUCCESS, "success"),
        (GitAPI.FAILURE, "failure"),
        (GitAPI.RUNNING, "pending"),
        (GitAPI.CANCELED, "error"),
        )
    REQUEST_TIMEOUT = 5

    def sign_in_url(self):
        return reverse('ci:github:sign_in')

    def repos_url(self, affiliation):
        return '{}/user/repos?affiliation={}'.format(self._api_url, affiliation)

    def git_url(self, owner, repo):
        return "git@github.com:%s/%s" % (owner, repo)

    def repo_url(self, owner, repo):
        return "%s/repos/%s/%s" % (self._api_url, owner, repo)

    def status_url(self, owner, repo, sha):
        return "%s/statuses/%s" % (self.repo_url(owner, repo), sha)

    def branches_url(self, owner, repo):
        return "%s/branches" % (self.repo_url(owner, repo))

    def branch_html_url(self, owner, repo, branch):
        return "%s/tree/%s" % (self.repo_html_url(owner, repo), branch)

    def branch_url(self, owner, repo, branch):
        return "%s/%s" % (self.branches_url(owner, repo), branch)

    def repo_html_url(self, owner, repo):
        return "%s/%s/%s" %(self._github_url, owner, repo)

    def commit_comment_url(self, owner, repo, sha):
        return "%s/commits/%s/comments" % (self.repo_url(owner, repo), sha)

    def commit_url(self, owner, repo, sha):
        return "%s/commits/%s" % (self.repo_url(owner, repo), sha)

    def commit_html_url(self, owner, repo, sha):
        return "%s/commits/%s" % (self.repo_html_url(owner, repo), sha)

    def collaborator_url(self, owner, repo, user):
        return "%s/collaborators/%s" % (self.repo_url(owner, repo), user)

    def pr_labels_url(self, owner, repo, pr_num):
        return "%s/issues/%s/labels" % (self.repo_url(owner, repo), pr_num)

    def pr_html_url(self, owner, repo, pr_num):
        return "%s/pull/%s" % (self.repo_html_url(owner, repo), pr_num)

    def pr_changed_files_url(self, owner, repo, pr_num):
        return "%s/pulls/%s/files" % (self.repo_url(owner, repo), pr_num)

    def status_str(self, status):
        for status_pair in self.STATUS:
            if status == status_pair[0]:
                return status_pair[1]
        return None

    def get_all_repos(self, auth_session, username):
        repos = self.get_user_repos(auth_session)
        repos.extend(self.get_user_org_repos(auth_session))
        return repos

    def get_user_repos(self, auth_session):
        response = auth_session.get(self.repos_url(affiliation='owner,collaborator'), timeout=self.REQUEST_TIMEOUT)
        data = self.get_all_pages(auth_session, response)
        owner_repo = []
        if 'message' not in data:
            for repo in data:
                owner_repo.append("%s/%s" % (repo['owner']['login'], repo['name']))
            owner_repo.sort()
        return owner_repo

    def get_repos(self, auth_session, session):
        if 'github_repos' in session:
            return session['github_repos']
        owner_repo = self.get_user_repos(auth_session)
        session['github_repos'] = owner_repo
        return owner_repo

    def get_branches(self, auth_session, owner, repo):
        response = auth_session.get(self.branches_url(owner, repo), timeout=self.REQUEST_TIMEOUT)
        data = self.get_all_pages(auth_session, response)
        branches = []
        if 'message' not in data:
            for branch in data:
                branches.append(branch['name'])
        branches.sort()
        return branches

    def get_user_org_repos(self, auth_session):
        response = auth_session.get(self.repos_url(affiliation='organization_member'), timeout=self.REQUEST_TIMEOUT)
        data = self.get_all_pages(auth_session, response)
        org_repo = []
        if 'message' not in data:
            for repo in data:
                org_repo.append("%s/%s" % (repo['owner']['login'], repo['name']))
            org_repo.sort()
        return org_repo

    def get_org_repos(self, auth_session, session):
        if 'github_org_repos' in session:
            return session['github_org_repos']
        org_repo = self.get_user_org_repos(auth_session)
        session['github_org_repos'] = org_repo
        return org_repo

    def update_pr_status(self, oauth_session, base, head, state, event_url, description, context, job_stage):
        if not settings.REMOTE_UPDATE:
            return

        data = {
            'state': self.status_str(state),
            'target_url': event_url,
            'description': description,
            'context': context,
            }
        url = self.status_url(base.user().name, base.repo().name, head.sha)
        try:
            response = oauth_session.post(url, data=json.dumps(data), timeout=self.REQUEST_TIMEOUT)
            if 'updated_at' not in response.content:
                logger.warning("Error setting pr status {}\nSent data: {}\nReply: {}".format(url, data, response.content))
            else:
                logger.info("Set pr status {}:\nSent Data: {}".format(url, data))
        except Exception as e:
            logger.warning("Error setting pr status {}\nSent data: {}\nError : {}".format(url, data, traceback.format_exc(e)))

    def remove_pr_todo_labels(self, builduser, owner, repo, pr_num):
        """
        Removes all labels on a PR with the labels that start with a certain prefix
        Input:
          builduser: models.Gituser that we will be sending the request as
          owner: str: name of the owner of the repo
          repo: str: name of the repository
          pr_num: int: PR number
        """
        if not settings.REMOTE_UPDATE:
            return

        url = self.pr_labels_url(owner, repo, pr_num)
        try:
            # First get a list of all labels
            oauth_session = GitHubAuth().start_session_for_user(builduser)
            response = oauth_session.get(url, timeout=self.REQUEST_TIMEOUT)
            response.raise_for_status()
            all_labels = self.get_all_pages(oauth_session, response)
            # We could filter out the unwanted labels and then POST the new list
            # but I don't like the message that appears on GitHub.
            # Instead, delete each one. This should be fine since there won't
            # be many of these.
            for label in all_labels:
                for remove_label in settings.GITHUB_REMOVE_PR_LABEL_PREFIX:
                    if label["name"].startswith(remove_label):
                        new_url = "%s/%s" % (url, label["name"])
                        response = oauth_session.delete(new_url)
                        response.raise_for_status()
                        logger.info("Removed label '%s' for %s/%s pr #%s" % (label["name"], owner, repo, pr_num))
                        break
        except Exception as e:
            logger.warning("Problem occured while removing labels for %s/%s pr #%s: %s" % (owner, repo, pr_num, e))

    def is_collaborator(self, oauth_session, user, repo):
        # first just check to see if the user is the owner
        if repo.user == user:
            return True
        # now ask github
        url = self.collaborator_url(repo.user.name, repo.name, user.name)
        logger.info('Checking {}'.format(url))
        response = oauth_session.get(url, timeout=self.REQUEST_TIMEOUT)
        # on success a 204 no content
        if response.status_code == 403:
            logger.info('User {} does not have permission to check collaborators on {}'.format(user, repo))
            return False
        elif response.status_code == 404:
            logger.info('User {} is NOT a collaborator on {}'.format(user, repo))
            return False
        elif response.status_code == 204:
            logger.info('User {} is a collaborator on {}'.format(user, repo))
            return True
        else:
            logger.info('Unknown response on collaborator check for user {} on {}. Status: {}\nResponse: {}'.format(user, repo, response.status_code, response.json()))
            return False

    def _post_data(self, oauth_session, url, post_data):
        """
        Post the given data to the URL
        """
        if not settings.REMOTE_UPDATE:
            return

        try:
            response = oauth_session.post(url, data=json.dumps(post_data), timeout=self.REQUEST_TIMEOUT)
            response.raise_for_status()
            data = response.json()
            logger.info("Posted to URL: %s\nPost data: %s\nRepsonse: %s" % (url, post_data, data))
            return data
        except Exception as e:
            logger.warning("Failed to post.\nURL: %s\nPost data: %s\nError: %s" %(url, post_data, traceback.format_exc(e)))

    def pr_comment(self, oauth_session, url, msg):
        """
        Post a comment to a PR
        """
        comment = {'body': msg}
        self._post_data(oauth_session, url, comment)

    def pr_job_status_comment(self, oauth_session, url, msg):
        """
        we don't actually use this on GitHub since we rely
        only on statuses
        """

    def pr_review_comment(self, oauth_session, url, sha, filepath, position, msg):
        """
        Post a review comment on a specific file position of a PR
        """
        comment = {'body': msg,
            "commit_id": sha,
            "path": filepath,
            "position": int(position),
            }
        self._post_data(oauth_session, url, comment)

    def last_sha(self, oauth_session, owner, repo, branch):
        """
        Get the latest SHA for a branch
        Input:
          auth_session: requests_oauthlib.OAuth2Session for the user making the requests
          owner: str: owner of the repository
          repo: str: name of the repository
          branch: str: name of the branch
        Return:
          Last SHA of the branch or None if there was a problem
        """
        url = self.branch_url(owner, repo, branch)
        try:
            response = oauth_session.get(url, timeout=self.REQUEST_TIMEOUT)
            response.raise_for_status()
            if 'commit' in response.content:
                data = json.loads(response.content)
                return data['commit']['sha']
            logger.warning("Unknown branch information for %s\nResponse: %s" % (url, response.content))
        except Exception as e:
            logger.warning("Failed to get branch information at %s.\nError: %s" % (url, traceback.format_exc(e)))

    def get_all_pages(self, oauth_session, response):
        """
        Utility function to get all the pages of a response and put all the data in one place.
        Input:
          auth_session: requests_oauthlib.OAuth2Session for the user making the requests
          response: Initial response as given by the requests module.
        """
        all_json = response.json()
        while 'next' in response.links:
            response = oauth_session.get(response.links['next']['url'], timeout=self.REQUEST_TIMEOUT)
            all_json.extend(response.json())
        return all_json

    def install_webhooks(self, auth_session, user, repo):
        """
        Updates the webhook for this server on GitHub.
        Input:
          auth_session: requests_oauthlib.OAuth2Session for the user updating the web hooks.
          user: models.GitUser of the user trying to update the web hooks.
          repo: models.Repository of the repository to set the web hook on.
        Raises:
          GitException if there are any errors.
        """
        if not settings.INSTALL_WEBHOOK:
            return

        hook_url = '%s/hooks' % self.repo_url(repo.user.name, repo.name)
        callback_url = "%s%s" % (settings.WEBHOOK_BASE_URL, reverse('ci:github:webhook', args=[user.build_key]))
        response = auth_session.get(hook_url, timeout=self.REQUEST_TIMEOUT)
        if response.status_code != 200:
            err = 'Failed to access webhook to {} for user {}\nurl: {}\nresponse: {}'.format(repo, user.name, hook_url, response.json())
            logger.warning(err)
            raise GitException(err)

        data = self.get_all_pages(auth_session, response)
        have_hook = False
        for hook in data:
            events = hook.get('events', [])
            if ('pull_request' not in events) or ('push' not in events):
                continue

            if hook['config']['url'] == callback_url and hook['config']['content_type'] == 'json':
                have_hook = True
                break

        if have_hook:
            return

        add_hook = {
            'name': 'web', # "web" is required for webhook
            'active': True,
            'events': ['push', 'pull_request'],
            'config': {
              'url': callback_url,
              'content_type': 'json',
              'insecure_ssl': '1',
              }
            }
        response = auth_session.post(hook_url, data=json.dumps(add_hook), timeout=self.REQUEST_TIMEOUT)
        data = response.json()
        if 'errors' in data:
            logger.warning('Failed to add webhook to {} for user {}\nurl: {}\nhook_data:{}\nresponse: {}'.format(repo, user.name, hook_url, add_hook, data))
            raise GitException(data['errors'])
        logger.info('Added webhook to %s for user %s' % (repo, user.name))

    def get_pr_changed_files(self, build_user, owner, repo, pr_num):
        """
        Gets a list of changed files in this PR.
        Input:
          build_user: models.GitUser: This will be the user that will be making the API call
          owner: str: name of the owner of the repo
          repo: str: name of the repository
          pr_num: int: PR number
        Return:
          list[str]: Filenames that have changed in the PR
        """
        if not settings.REMOTE_UPDATE:
            return []
        auth_session = build_user.start_session()
        url = self.pr_changed_files_url(owner, repo, pr_num)
        try:
            response = auth_session.get(url, timeout=self.REQUEST_TIMEOUT)
            data = self.get_all_pages(auth_session, response)
            filenames = []
            if 'message' not in data:
                filenames = [ f['filename'] for f in data ]
                filenames.sort()
            return filenames
        except Exception as e:
            logger.warning("Failed to get PR changed files at URL: %s\nError: %s" % (url, e))
            return []
