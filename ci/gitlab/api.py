
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
from django.conf import settings
import logging, traceback
import json
import urllib, requests
from ci.git_api import GitAPI, GitException

logger = logging.getLogger('ci')

class GitLabAPI(GitAPI):
    _api_url = '{}/api/v3'.format(settings.GITLAB_API_URL)
    _html_url = settings.GITLAB_API_URL
    STATUS = ((GitAPI.PENDING, "pending"),
        (GitAPI.ERROR, "failed"),
        (GitAPI.SUCCESS, "success"),
        (GitAPI.FAILURE, "failed"),
        (GitAPI.RUNNING, "running"),
        (GitAPI.CANCELED, "canceled"),
        )

    def post(self, url, token, data, timeout=20):
        params = {'private_token': token}
        return requests.post(url, params=params, data=data, verify=settings.GITLAB_SSL_CERT, timeout=timeout)

    def git_url(self, owner, repo):
        return "git@%s:%s/%s" % (settings.GITLAB_HOSTNAME, owner, repo)

    def get(self, url, token, extra_args={}, timeout=10):
        extra_args['private_token'] = token
        extra_args['per_page'] = 100
        logger.debug('Getting url {} with token = {}'.format(url, token))
        return requests.get(url, params=extra_args, verify=settings.GITLAB_SSL_CERT, timeout=timeout)

    def sign_in_url(self):
        return reverse('ci:gitlab:sign_in')

    def users_url(self):
        return "%s/users" % self._api_url

    def user_url(self, author_id):
        return "%s/%s" % (self.users_url(), author_id)

    def repos_url(self):
        return "%s/projects/owned" % self._api_url

    def orgs_url(self):
        return "%s/user/orgs" % self._api_url

    def projects_url(self):
        return "%s/projects" % (self._api_url)

    def gitlab_id(self, owner, repo):
        name = '{}/{}'.format(owner, repo)
        return urllib.quote_plus(name)

    def repo_url(self, owner, repo):
        return '{}/{}'.format(self.projects_url(), self.gitlab_id(owner, repo))

    def branches_url(self, owner, repo):
        return "%s/repository/branches" % (self.repo_url(owner, repo))

    def branch_by_id_url(self, repo_id, branch_id):
        return "%s/%s/repository/branches/%s" % (self.projects_url(), repo_id, urllib.quote_plus(str(branch_id)))

    def branch_url(self, owner, repo, branch):
        return "%s/%s" % (self.branches_url(owner, repo), urllib.quote_plus(str(branch)))

    def branch_html_url(self, owner, repo, branch):
        return "%s/tree/%s" % (self.repo_html_url(owner, repo), branch)

    def repo_html_url(self, owner, repo):
        return '{}/{}/{}'.format(self._html_url, owner, repo)

    def comment_api_url(self, project_id, pr_id):
        return '{}/projects/{}/merge_request/{}/comments'.format(self._api_url, project_id, pr_id)

    def commit_html_url(self, owner, repo, sha):
        return '{}/commit/{}'.format(self.repo_html_url(owner, repo), sha)

    def pr_html_url(self, owner, repo, pr_iid):
        return '{}/merge_requests/{}'.format(self.repo_html_url(owner, repo),  pr_iid)

    def pr_changed_files_url(self, owner, repo, pr_id):
        return '{}/projects/{}/merge_request/{}/changes'.format(self._api_url, self.gitlab_id(owner, repo), pr_id)

    def internal_pr_html_url(self, repo_path, pr_iid):
        return '{}/{}/merge_requests/{}'.format(self._html_url, repo_path, pr_iid)

    def members_url(self, owner, repo):
        return "%s/members" % (self.repo_url(owner, repo))

    def project_members_url(self, owner, repo, user_id):
        return "%s/%s" % (self.members_url(owner, repo), user_id)

    def groups_url(self):
        return "%s/groups" % (self._api_url)

    def group_members_url(self, group_id):
        return "%s/%s/members" % (self.groups_url(), group_id)

    def get_token(self, auth_session):
        return auth_session.token['access_token']

    def get_all_repos(self, auth_session, owner):
        repos = self.get_user_repos(auth_session, owner)
        repos.extend(self.get_user_org_repos(auth_session, owner))
        return repos

    def get_user_repos(self, auth_session, username):
        token = self.get_token(auth_session)
        response = self.get(self.repos_url(), token)
        data = self.get_all_pages(auth_session, response)
        owner_repo = []
        for repo in data:
            owner = repo['namespace']['name']
            if owner == username:
                owner_repo.append("%s/%s" % (owner, repo['name']))
        owner_repo.sort()
        return owner_repo

    def get_repos(self, auth_session, session):
        if 'gitlab_repos' in session:
            return session['gitlab_repos']

        owner_repo = self.get_user_repos(auth_session, session['gitlab_user'])
        session['gitlab_repos'] = owner_repo
        return owner_repo

    def get_branches(self, auth_session, owner, repo):
        token = self.get_token(auth_session)
        response = self.get(self.branches_url(owner, repo), token)
        data = self.get_all_pages(auth_session, response)
        branches = []
        for branch in data:
            branches.append(branch['name'])
        branches.sort()
        return branches

    def get_user_org_repos(self, auth_session, username):
        token = self.get_token(auth_session)
        response = self.get(self.projects_url(), token)
        data = self.get_all_pages(auth_session, response)
        org_repo = []
        for repo in data:
            org = repo['namespace']['name']
            if org != username:
                org_repo.append('{}/{}'.format(org, repo['name']))
        org_repo.sort()
        return org_repo

    def get_org_repos(self, auth_session, session):
        if 'gitlab_org_repos' in session:
            return session['gitlab_org_repos']

        org_repos = self.get_user_org_repos(auth_session, session['gitlab_user'])
        session['gitlab_org_repos'] = org_repos
        return org_repos

    def status_str(self, status):
        for status_pair in self.STATUS:
            if status == status_pair[0]:
                return status_pair[1]
        return None

    def status_url(self, owner, repo, sha):
        return "%s/statuses/%s" % (self.repo_url(owner, repo), sha)

    def update_pr_status(self, oauth_session, base, head, state, event_url, description, context, job_stage):
        """
        This updates the status of a paritcular commit associated with a PR.
        """
        if not settings.REMOTE_UPDATE:
            return

        if job_stage == self.STATUS_CONTINUE_RUNNING:
            return

        data = {
            'id': self.gitlab_id(head.user().name, head.repo().name),
            'sha': head.sha,
            'ref': head.branch.name,
            'state': self.status_str(state),
            'target_url': event_url,
            'description': description,
            'name': context,
            }
        url = self.status_url(head.user().name, head.repo().name, head.sha)
        try:
            token = self.get_token(oauth_session)
            response = self.post(url, token, data=data)
            if response.status_code not in [200, 201, 202]:
                logger.warning("Error setting pr status {}\nSent data: {}\nReply: {}".format(url, data, response.content))
            else:
                logger.info("Set pr status {}:\nSent Data: {}".format(url, data))
        except Exception as e:
            logger.warning("Error setting pr status {}\nSent data: {}\nError : {}".format(url, data, traceback.format_exc(e)))

    def get_group_id(self, oauth, token, username):
        """
        Finds the group id of the username.
        """
        response = self.get(self.groups_url(), token)
        data = self.get_all_pages(oauth, response)
        for group in data:
            if group.get('name') == username:
                return group['id']

    def is_group_member(self, oauth, token, group_id, username):
        """
        Returns where the user is a member of the group_id
        """
        response = self.get(self.group_members_url(group_id), token)
        data = self.get_all_pages(oauth, response)
        for member in data:
            if member.get('username') == username:
                return True
        return False

    def is_collaborator(self, oauth_session, user, repo):
        """
        Checks to see if the user is a collaborator
        on the repo.
        """
        # first just check to see if the user is the owner
        if repo.user == user:
            return True
        # now ask gitlab
        url = self.members_url(repo.user.name, repo.name)
        token = self.get_token(oauth_session)
        response = self.get(url, token)
        data = self.get_all_pages(oauth_session, response)
        for member in data:
            if isinstance(member, dict) and member.get('username') == user.name:
                return True

        # not a member, check groups.
        # We first need to find the group_id
        group_id = self.get_group_id(oauth_session, token, repo.user.name)
        if not group_id:
            return False

        return self.is_group_member(oauth_session, token, group_id, user.name)

    def pr_review_comment(self, oauth_session, url, sha, filepath, position, msg):
        """
        FIXME: Disabled for now.
        if not settings.REMOTE_UPDATE:
          return

        comment = {'note': msg,
            "sha": sha,
            "id": ,
            "path": filepath,
            "line": position,
            }
        try:
          token = self.get_token(oauth_session)
          logger.info('POSTing to {}:{}: {}'.format(url, token, comment))
          response = self.post(url, token, data=comment)
          logger.info('Response: {}'.format(response.json()))
        except Exception as e:
          logger.warning("Failed to leave commit comment.\nComment: %s\nError: %s" %(msg, traceback.format_exc(e)))
        """

    def pr_job_status_comment(self, oauth_session, url, msg):
        """
        Doesn't need to do anything special, just call pr_comment
        """
        self.pr_comment(oauth_session, url, msg)

    def pr_comment(self, oauth_session, url, msg):
        """
        Post a comment to a PR
        """
        if not settings.REMOTE_UPDATE:
            return

        comment = {'note': msg}
        try:
            token = self.get_token(oauth_session)
            logger.info('POSTing to {}:{}: {}'.format(url, token, comment))
            response = self.post(url, token, data=comment)
            logger.info('Response: {}'.format(response.json()))
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
        callback_url = "%s%s" % (settings.WEBHOOK_BASE_URL, reverse('ci:gitlab:webhook', args=[user.build_key]))
        token = self.get_token(auth_session)
        response = self.get(hook_url, token)
        data = self.get_all_pages(auth_session, response)
        have_hook = False
        for hook in data:
            if hook.get('merge_requests_events') and hook.get('push_events') and hook.get('url') == callback_url:
                have_hook = True
                break

        if have_hook:
            return None

        add_hook = {
            'id': self.gitlab_id(repo.user.name, repo.name),
            'url': callback_url,
            'push_events': 'true',
            'merge_requests_events': 'true',
            'issues_events': 'false',
            'tag_push_events': 'false',
            'note_events': 'false',
            'enable_ssl_verification': 'false',
            }
        response = self.post(hook_url, token, add_hook)
        if response.status_code >= 400:
            raise GitException(response.json())
        logger.debug('Added webhook to %s for user %s' % (repo, user.name))

    def get_pr_changed_files(self, auth_session, owner, repo, pr_id):
        token = self.get_token(auth_session)
        url = self.pr_changed_files_url(owner, repo, pr_id)
        try:
            response = self.get(url, token)
            response.raise_for_status()
            data = self.get_all_pages(auth_session, response)
            filenames = [ f['new_path'] for f in data['changes'] ]
            filenames.sort()

            if not filenames:
                logger.warning("Didn't read any PR changed files at URL: %s\nData: %s" % (url, data))
            return filenames
        except Exception as e:
            logger.warning("Failed to get PR changed files at URL: %s\nError: %s" % (url, e))
            return []

    def get_project_access_level(self, auth_session, owner, repo):
        """
        Gets the access level for a project for the current authorized user.
        Input:
          auth_session: requests_oauthlib.OAuth2Session for the user updating the web hooks.
          owner[str]: owner of the project
          repo[str]: name of the repo
        """
        token = self.get_token(auth_session)
        try:
            # This will get the info on the currently authorized user
            url = "%s/user" % self._api_url
            response = self.get(url, token)
            if response.status_code != 200:
                return "Unknown"
            data = response.json()
            user_id = data.get("id")

            url = self.project_members_url(owner, repo, user_id)
            response = self.get(url, token)
            if response.status_code != 200:
                return "Unknown"
            data = response.json()
            access_level = data.get("access_level")
            access_level_map = {10: "Guest", 20: "Reporter", 30: "Developer", 40: "Master", 50: "Owner"}
            return access_level_map.get(access_level, "Unknown")
        except Exception as e:
            logger.warning("Failed to determine permission level: %s" % e)
            return "Unknown"
