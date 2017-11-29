
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
import urllib, requests
from ci.git_api import GitAPI, GitException
import re

logger = logging.getLogger('ci')

class GitLabAPI(GitAPI):
    STATUS = ((GitAPI.PENDING, "pending"),
        (GitAPI.ERROR, "failed"),
        (GitAPI.SUCCESS, "success"),
        (GitAPI.FAILURE, "failed"),
        (GitAPI.RUNNING, "running"),
        (GitAPI.CANCELED, "canceled"),
        )

    def __init__(self, config):
        super(GitLabAPI, self).__init__()
        self._config = config
        self._api_url = '%s/api/v4' % config.get("api_url", "")
        self._html_url = config.get("html_url", "")
        self._request_timeout = config.get("request_timeout", 5)
        self._install_webhook = config.get("install_webhook", False)
        self._update_remote = config.get("remote_update", False)
        self._remove_pr_labels = config.get("remove_pr_label_prefix", [])
        self._civet_url = config.get("civet_base_url", "")
        self._ssl_cert = config.get("ssl_cert", False)
        self._hostname = config.get("hostname")[0]
        self._prefix = "%s_" % config["hostname"]
        self._repos_key = "%s_repos" % self._prefix
        self._org_repos_key = "%s_org_repos" % self._prefix
        self._user_key= "%s_user" % self._prefix

    def post(self, url, token, data, timeout=20):
        params = {'private_token': token}
        return requests.post(url, params=params, data=data, verify=self._ssl_cert, timeout=timeout)

    def delete(self, url, token, timeout=10):
        params = {'private_token': token}
        return requests.delete(url, params=params, verify=self._ssl_cert, timeout=timeout)

    def put(self, url, token, data, timeout=10):
        params = {'private_token': token}
        return requests.put(url, params=params, data=data, verify=self._ssl_cert, timeout=timeout)

    def git_url(self, owner, repo):
        return "git@%s:%s/%s" % (self._hostname, owner, repo)

    def get(self, url, token, extra_args={}, timeout=10):
        extra_args['private_token'] = token
        extra_args['per_page'] = 100
        logger.debug('Getting url {} with token = {}'.format(url, token))
        return requests.get(url, params=extra_args, verify=self._ssl_cert, timeout=timeout)

    def sign_in_url(self):
        return reverse('ci:gitlab:sign_in', args=[self._config["hostname"]])

    def user_url(self, author_id):
        return "%s/users/%s" % (self._api_url, author_id)

    def gitlab_id(self, owner, repo):
        name = '{}/{}'.format(owner, repo)
        return urllib.quote_plus(name)

    def repo_url(self, owner, repo):
        return '%s/projects/%s' % (self._api_url, self.gitlab_id(owner, repo))

    def project_url(self, project_id):
        return "%s/projects/%s" % (self._api_url, project_id)

    def branches_url(self, owner, repo):
        return "%s/repository/branches" % (self.repo_url(owner, repo))

    def branch_by_id_url(self, repo_id, branch_id):
        return "%s/projects/%s/repository/branches/%s" % (self._api_url, repo_id, urllib.quote_plus(str(branch_id)))

    def branch_url(self, owner, repo, branch):
        return "%s/%s" % (self.branches_url(owner, repo), urllib.quote_plus(str(branch)))

    def branch_html_url(self, owner, repo, branch):
        return "%s/tree/%s" % (self.repo_html_url(owner, repo), branch)

    def repo_html_url(self, owner, repo):
        return '{}/{}/{}'.format(self._html_url, owner, repo)

    def comment_api_url(self, project_id, pr_iid):
        return '{}/projects/{}/merge_requests/{}/notes'.format(self._api_url, project_id, pr_iid)

    def commit_html_url(self, owner, repo, sha):
        return '{}/commit/{}'.format(self.repo_html_url(owner, repo), sha)

    def pr_html_url(self, owner, repo, pr_iid):
        return '{}/merge_requests/{}'.format(self.repo_html_url(owner, repo),  pr_iid)

    def pr_changed_files_url(self, owner, repo, pr_iid):
        return '{}/projects/{}/merge_requests/{}/changes'.format(self._api_url, self.gitlab_id(owner, repo), pr_iid)

    def internal_pr_html_url(self, repo_path, pr_iid):
        return '{}/{}/merge_requests/{}'.format(self._html_url, repo_path, pr_iid)

    def get_token(self, auth_session):
        return auth_session.token['access_token']

    def get_all_repos(self, auth_session, owner):
        repos = self.get_user_repos(auth_session, owner)
        repos.extend(self.get_user_org_repos(auth_session, owner))
        return repos

    def get_user_repos(self, auth_session, username):
        token = self.get_token(auth_session)
        owned_repos_url = "%s/projects" % self._api_url
        get_data = {"simple": True}
        response = self.get(owned_repos_url, token, get_data)
        data = self.get_all_pages(auth_session, response)
        owner_repo = []
        for repo in data:
            r = repo["path_with_namespace"]
            if r.startswith("%s/" % username):
                owner_repo.append(r)
        owner_repo.sort()
        return owner_repo

    def get_repos(self, auth_session, session):
        if self._repos_key in session:
            return session[self._repos_key]

        owner_repo = self.get_user_repos(auth_session, session.get(self._user_key, ""))
        session[self._repos_key] = owner_repo
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
        proj_url = "%s/projects" % self._api_url
        get_data = {"simple": True}
        response = self.get(proj_url, token, get_data)
        data = self.get_all_pages(auth_session, response)
        org_repo = []
        for repo in data:
            org = repo['path_with_namespace']
            if not org.startswith("%s/" % username):
                org_repo.append(org)
        org_repo.sort()
        return org_repo

    def get_org_repos(self, auth_session, session):
        if self._org_repos_key in session:
            return session[self._org_repos_key]

        org_repos = self.get_user_org_repos(auth_session, session[self._user_key])
        session[self._org_repos_key] = org_repos
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
        if not self._update_remote:
            return

        if job_stage in [self.STATUS_START_RUNNING, self.STATUS_CONTINUE_RUNNING]:
            # GitLab doesn't like setting status to running multiple times
            # and there is no point since we are only updating the description
            # and that doesn't show up anywhere
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
        url = "%s/groups" % self._api_url
        response = self.get(url, token)
        data = self.get_all_pages(oauth, response)
        for group in data:
            if group.get('name') == username:
                return group['id']

    def is_group_member(self, oauth, token, group_id, username):
        """
        Returns where the user is a member of the group_id
        """
        url = "%s/groups/%s/members" % (self._api_url, group_id)
        response = self.get(url, token)
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
        url = "%s/users" % self.repo_url(repo.user.name, repo.name)
        token = self.get_token(oauth_session)
        extra = {"search": user.name}
        try:
            response = self.get(url, token, extra)
            response.raise_for_status()
            data = response.json()
            for member in data:
                if member.get('username') == user.name:
                    return True
        except Exception as e:
            logger.warning("Error checking if %s is a member of %s at %s\nError : %s" % (user, repo, url, traceback.format_exc(e)))

        return False

    def pr_review_comment(self, oauth_session, url, sha, filepath, position, msg):
        """
        FIXME: Disabled for now.
        if not self._update_remote:
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

    def pr_comment(self, oauth_session, url, msg):
        """
        Post a comment to a PR
        """
        if not self._update_remote:
            return

        try:
            comment = {'body': msg}
            token = self.get_token(oauth_session)
            logger.info('POSTing to {}:{}: {}'.format(url, token, comment))
            response = self.post(url, token, data=comment)
            logger.info('Response: {}'.format(response.json()))
            response.raise_for_status()
        except Exception as e:
            logger.warning("Failed to leave comment at %s.\nComment: %s\nError: %s" %(url, msg, traceback.format_exc(e)))

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
        if not self._install_webhook:
            return

        hook_url = '%s/hooks' % self.repo_url(repo.user.name, repo.name)
        callback_url = "%s%s" % (self._civet_url, reverse('ci:gitlab:webhook', args=[user.build_key]))
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
        access_level_map = {10: "Guest", 20: "Reporter", 30: "Developer", 40: "Master", 50: "Owner"}
        url = "%s/user" % self._api_url
        user_id = None
        try:
            # This will get the info on the currently authorized user
            response = self.get(url, token)
            response.raise_for_status()
            data = response.json()
            user_id = data["id"]
        except Exception as e:
            logger.warning("Failed to get user information for signed in user at %s : %s" % (url, e))
            return "Unknown"

        # /projects/<project>/users doesn't seem to give the access level, so use members
        url = "%s/members/%s" % (self.repo_url(owner, repo), user_id)
        try:
            response = self.get(url, token)
            response.raise_for_status()
            data = response.json()
            access_level = data.get("access_level")
            return access_level_map.get(access_level, "Unknown")
        except Exception as e:
            logger.warning("Failed to determine permission level for %s/%s at %s. "
                "The signed in user is likely not a member. Error: %s" % (owner, repo, url, e))

        # If we get here then the signed in user is not in projects/members but could
        # be in groups/members. GitLab API sucks. See https://gitlab.com/gitlab-org/gitlab-ce/issues/18672
        url = self.repo_url(owner, repo)
        try:
            response = self.get(url, token)
            response.raise_for_status()
            data = response.json()
            namespace = data.get("namespace")
            group_id = namespace.get("id")

            url = "%s/groups/%s/members/%s" % (self._api_url, group_id, user_id)
            response = self.get(url, token)
            response.raise_for_status()
            data = response.json()
            access_level = data.get("access_level")
            return access_level_map.get(access_level, "Unknown")
        except Exception as e:
            logger.warning("Failed to determine permission level for %s/%s at %s. "
                    "The signed in user is likely not a group member. Error: %s" % (owner, repo, url, e))
        return "Unknown"

    def add_pr_label(self, builduser, repo, pr_num, label_name):
        logger.warning("GitLab function not implemented: add_pr_label")

    def remove_pr_label(self, builduser, repo, pr_num, label_name):
        logger.warning("GitLab function not implemented: remove_pr_label")

    def get_pr_comments(self, oauth, url, username, comment_re):
        if not self._update_remote:
            return []

        try:
            token = self.get_token(oauth)
            response = self.get(url, token)
            response.raise_for_status()
            data = self.get_all_pages(oauth, response)
            comments = []
            for c in data:
                if c["author"]["username"] != username:
                    continue
                if re.search(comment_re, c["body"]):
                    c["url"] = "%s/%s" % (url, c["id"])
                    comments.append(c)
            return comments
        except Exception as e:
            logger.warning("Failed to get PR comments at URL: %s\nError: %s" % (url, e))
            return []

    def remove_pr_comment(self, oauth, comment):
        """
        Remove a comment from a PR.
        """
        if not self._update_remote:
            return

        del_url = comment.get("url")
        try:
            token = self.get_token(oauth)
            response = self.delete(del_url, token)
            response.raise_for_status()
            logger.info("Removed comment: %s" % del_url)
        except Exception as e:
            logger.warning("Failed to remove PR comment at URL: %s\nError: %s" % (del_url, e))

    def edit_pr_comment(self, oauth, comment, msg):
        """
        Edit a comment on a PR.
        """
        if not self._update_remote:
            return

        edit_url = comment.get("url")
        try:
            token = self.get_token(oauth)
            response = self.put(edit_url, token, data={"body": msg})
            response.raise_for_status()
            logger.info("Edited PR comment at %s" % edit_url)
        except Exception as e:
            logger.warning("Failed to edit PR comment at URL: %s\nError: %s" % (edit_url, e))

    def is_member(self, oauth, team, user):
        """
        Checks to see if a user is a member of the team/group
        """
        if user.name == team:
            return True
        token = self.get_token(oauth)
        return self.is_group_member(oauth, token, team, user.name)

    def get_open_prs(self, oauth, owner, repo):
        url = "%s/merge_requests" % self.repo_url(owner, repo)
        params = {"state": "opened"}
        try:
            token = self.get_token(oauth)
            response = self.get(url, token, params)
            response.raise_for_status()
            data = self.get_all_pages(oauth, response)
            open_prs = []
            for pr in data:
                open_prs.append({"number": pr["iid"], "title": pr["title"], "html_url": pr["web_url"]})
            return open_prs
        except Exception as e:
            logger.warning("Failed to get open PRs for %s/%s at URL: %s\nError: %s" % (owner, repo, url, e))
