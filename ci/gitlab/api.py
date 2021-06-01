
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

from __future__ import unicode_literals, absolute_import
from django.urls import reverse
import logging
import requests
from ci.git_api import GitAPI, GitException, copydoc
import re
import json
try:
    from urllib.parse import quote_plus, urljoin
except ImportError:
    from urllib import quote_plus
    from urlparse import urljoin

logger = logging.getLogger('ci')

class GitLabAPI(GitAPI):
    STATUS = ((GitAPI.PENDING, "pending"),
        (GitAPI.ERROR, "failed"),
        (GitAPI.SUCCESS, "success"),
        (GitAPI.FAILURE, "failed"),
        (GitAPI.RUNNING, "running"),
        (GitAPI.CANCELED, "canceled"),
        )

    def __init__(self, config, access_user=None, token=None):
        super(GitLabAPI, self).__init__(config, access_user=access_user,  token=token)
        self._api_url = '%s/api/v4' % config.get("api_url", "")
        self._hostname = config.get("hostname", "unknown_gitlab")
        self._prefix = "%s_" % self._hostname
        self._html_url = config.get("html_url", "")
        self._ssl_cert = config.get("ssl_cert", False)
        self._repos_key = "%s_repos" % self._prefix
        self._org_repos_key = "%s_org_repos" % self._prefix
        self._user_key= "%s_user" % self._prefix

        if access_user is not None and access_user.token:
            token = json.loads(access_user.token)
            # For backwards compatability, users that haven't signed in
            # with the new OAuth2 application, their current token
            # is a private token which requires a different http header to be set.
            # The OAuth2 token data has the "token_type" key
            # while the private token data just has the "access_token" key
            if "token_type" in token:
                self._session = self._access_user.start_session()
            else:
                self._headers["PRIVATE-TOKEN"] = token.get("access_token")
                self._session = requests
        elif self._token is not None:
            # We assume the token that is passed in is a personal access token
            # or private token
            self._headers["PRIVATE-TOKEN"] = self._token
            self._session = requests
        else:
            self._session = requests

    @copydoc(GitAPI.sign_in_url)
    def sign_in_url(self):
        return reverse('ci:gitlab:sign_in', args=[self._hostname])

    def _gitlab_id(self, owner, repo):
        name = '%s/%s' % (owner, repo)
        return quote_plus(name)

    def _repo_url(self, path_with_namespace):
        return '%s/projects/%s' % (self._api_url, quote_plus(path_with_namespace))

    def _project_url(self, project_id):
        """
        Get the projects API URL based on project ID.
        Input:
            project_id[int]: Project ID
        """
        return "%s/projects/%s" % (self._api_url, project_id)

    def _branch_by_id_url(self, repo_id, branch_id):
        """
        Get the branch API URL using IDs instead of owner/repo/branch.
        Input:
            repo_id[int]: ID of the repo
            branch_id[int]: ID of the branch
        """
        return "%s/projects/%s/repository/branches/%s" % (self._api_url, repo_id, quote_plus(str(branch_id)))

    @copydoc(GitAPI.branch_html_url)
    def branch_html_url(self, owner, repo, branch):
        return "%s/tree/%s" % (self.repo_html_url(owner, repo), branch)

    @copydoc(GitAPI.repo_html_url)
    def repo_html_url(self, owner, repo):
        return "%s/%s/%s" % (self._html_url, owner, repo)

    def _comment_api_url(self, project_id, pr_iid):
        """
        Get the API URL for a comment.
        Input:
            project_id[int]: ID of the project
            pr_iid[int]: Repo internal MR ID
        """
        return "%s/projects/%s/merge_requests/%s/notes" % (self._api_url, project_id, pr_iid)

    @copydoc(GitAPI.commit_html_url)
    def commit_html_url(self, owner, repo, sha):
        return '%s/commit/%s' % (self.repo_html_url(owner, repo), sha)

    def _pr_html_url(self, repo_path, pr_iid):
        return '{}/{}/merge_requests/{}'.format(self._html_url, repo_path, pr_iid)

    @copydoc(GitAPI.get_all_repos)
    def get_all_repos(self, owner):
        repos = self._get_user_repos(owner)
        repos.extend(self._get_user_org_repos(owner))
        return repos

    def _get_user_repos(self, username):
        """
        Gets a list of repos username owns or is a collaborator on.
        """
        url = "%s/projects" % self._api_url
        get_data = {"simple": True}
        data = self.get_all_pages(url, params=get_data)
        owner_repo = []
        if not self._bad_response and data:
            for repo in data:
                r = repo["path_with_namespace"]
                if r.startswith("%s/" % username):
                    owner_repo.append(r)
            owner_repo.sort()
        return owner_repo

    @copydoc(GitAPI.get_repos)
    def get_repos(self, session):
        if self._repos_key in session:
            return session[self._repos_key]

        username = session.get(self._user_key, "")
        if username:
            owner_repo = self._get_user_repos(username)
            session[self._repos_key] = owner_repo
        return owner_repo

    @copydoc(GitAPI.get_branches)
    def get_branches(self, path_with_namespace):
        url = "%s/repository/branches" % (self._repo_url(path_with_namespace))
        data = self.get_all_pages(url)
        branches = []
        if not self._bad_response and data:
            for branch in data:
                branches.append(branch['name'])
            branches.sort()
        return branches

    def _get_user_org_repos(self, username):
        """
        Get a list of organizations that the user is a member of.
        """
        url = "%s/projects" % self._api_url
        get_data = {"simple": True}
        data = self.get_all_pages(url, params=get_data)
        org_repo = []
        if not self._bad_response and data:
            for repo in data:
                org = repo['path_with_namespace']
                if not org.startswith("%s/" % username):
                    org_repo.append(org)
            org_repo.sort()
        return org_repo

    def _status_str(self, status):
        """
        Used to convert a GitAPI status into a string that GitLab wants.
        """
        for status_pair in self.STATUS:
            if status == status_pair[0]:
                return status_pair[1]
        return None

    @copydoc(GitAPI.update_pr_status)
    def update_pr_status(self, base, head, state, event_url, description, context, job_stage):
        """
        This updates the status of a paritcular commit associated with a PR.
        """
        if not self._update_remote:
            return

        if job_stage in [self.STATUS_START_RUNNING, self.STATUS_CONTINUE_RUNNING]:
            # GitLab doesn't like setting status to "running" multiple times
            # and there is no point since we are only updating the description
            # and that doesn't show up anywhere
            return

        path_with_namespace = "%s/%s" % (head.user().name, head.repo().name)
        data = {
            'id': quote_plus(path_with_namespace),
            'sha': head.sha,
            'ref': head.branch.name,
            'state': self._status_str(state),
            'target_url': event_url,
            'description': description,
            'name': context,
            }
        url = "%s/statuses/%s?state=%s" % (self._repo_url(path_with_namespace),
                                           head.sha,
                                           self._status_str(state))
        response = self.post(url, data=data)
        if not self._bad_response and response.status_code not in [200, 201, 202]:
            logger.warning("Error setting pr status %s\nSent data:\n%s\nReply:\n%s" % \
                    (url, self._format_json(data), self._format_json(response.json())))
        elif not self._bad_response:
            logger.info("Set pr status %s:\nSent Data:\n%s" % (url, self._format_json(data)))

    def _is_group_member(self, group_id, username):
        """
        Returns whether the user is a member of the group_id
        """
        url = "%s/groups/%s/members" % (self._api_url, group_id)
        data = self.get_all_pages(url)
        if not self._bad_response or data:
            for member in data:
                if member.get('username') == username:
                    return True
        return False

    @copydoc(GitAPI.is_collaborator)
    def is_collaborator(self, user, repo):
        if repo.user == user:
            # the user is the owner
            return True

        path_with_namespace = '%s/%s' % (repo.user.name, repo.name)
        url = "%s/users" % self._repo_url(path_with_namespace)
        extra = {"search": user.name}

        response = self.get(url, params=extra)
        if not self._bad_response:
            data = response.json()
            for member in data:
                if member.get('username') == user.name:
                    return True
        return False

    @copydoc(GitAPI.pr_comment)
    def pr_comment(self, url, msg):
        if not self._update_remote:
            return

        comment = {'body': msg}
        self.post(url, data=comment)
        if not self._bad_response:
            logger.info("Posted comment to %s.\nComment: %s" %(url, msg))
        else:
            self._add_error("Failed to leave comment at %s.\nComment: %s" %(url, msg))

    @copydoc(GitAPI.last_sha)
    def last_sha(self, owner, repo, branch):
        path_with_namespace = '%s/%s' % (owner, repo)
        url = "%s/repository/branches/%s" % (self._repo_url(path_with_namespace), quote_plus(str(branch)))
        response = self.get(url)
        if not self._bad_response:
            data = response.json()
            return data['commit']['id']

    @copydoc(GitAPI.install_webhooks)
    def install_webhooks(self, user, repo):
        """
        Updates the webhook for this server on GitHub.
        Input:
          user[models.GitUser]: The user trying to update the web hooks.
          repo[models.Repository]: The repository to set the web hook on.
        Raises:
          GitException if there are any errors.
        """
        if not self._install_webhook:
            return
        path_with_namespace = '%s/%s' % (repo.user.name, repo.name)
        hook_url = '%s/hooks' % self._repo_url(path_with_namespace)
        callback_url = urljoin(self._civet_url, reverse('ci:gitlab:webhook', args=[user.build_key]))
        data = self.get_all_pages(hook_url)

        have_hook = False
        if not self._bad_response and data:
            for hook in data:
                if hook.get('merge_requests_events') and hook.get('push_events') and hook.get('url') == callback_url:
                    have_hook = True
                    break

        if have_hook:
            return

        add_hook = {
            'id': self._gitlab_id(repo.user.name, repo.name),
            'url': callback_url,
            'push_events': 'true',
            'merge_requests_events': 'true',
            'issues_events': 'false',
            'tag_push_events': 'false',
            'note_events': 'false',
            'enable_ssl_verification': 'false',
            }
        response = self.post(hook_url, data=add_hook)
        if self._bad_response:
            raise GitException(self._format_json(response.json()))
        logger.info('Added webhook to %s for user %s' % (repo, user.name))

    def _get_pr_changed_files(self, owner, repo, pr_iid):
        """
        Gets a list of changed files in this PR.
        Input:
          owner[str]: name of the owner of the repo
          repo[str]: name of the repository
          pr_num[int]: PR number
        Return:
          list[str]: Filenames that have changed in the PR
        """
        url = "%s/projects/%s/merge_requests/%s/changes" % (self._api_url, self._gitlab_id(owner, repo), pr_iid)
        data = self.get_all_pages(url)
        filenames = []
        if not self._bad_response and data:
            filenames = [ f['new_path'] for f in data['changes'] ]
            filenames.sort()

        if not filenames and not self._bad_response:
            self._add_error("Didn't read any PR changed files at URL: %s\nData:\n%s" % (url, self._format_json(data)))
        return filenames

    def _get_project_access_level(self, path_with_namespace):
        """
        Gets the access level for a project for the current authorized user.
        Input:
          owner[str]: owner of the project
          repo[str]: name of the repo
        """
        access_level_map = {10: "Guest", 20: "Reporter", 30: "Developer", 40: "Master", 50: "Owner"}
        url = "%s/user" % self._api_url
        user_id = None
        # This will get the info on the currently authorized user
        response = self.get(url)
        if self._bad_response:
            return "Unknown"

        data = response.json()
        user_id = data.get("id")
        if not user_id:
            return "Unknown"

        # /projects/<project>/users doesn't seem to give the access level, so use members
        url = "%s/members/%s" % (self._repo_url(path_with_namespace), user_id)
        response = self.get(url)
        if not self._bad_response:
            data = response.json()
            access_level = data.get("access_level")
            return access_level_map.get(access_level, "Unknown")

        # If we get here then the signed in user is not in projects/members but could
        # be in groups/members. GitLab API sucks. See https://gitlab.com/gitlab-org/gitlab-ce/issues/18672
        url = self._repo_url(path_with_namespace)
        response = self.get(url)
        if self._bad_response:
            return "Unknown"

        data = response.json()
        namespace = data.get("namespace")
        group_id = namespace.get("id")

        url = "%s/groups/%s/members/%s" % (self._api_url, group_id, user_id)
        response = self.get(url)
        if self._bad_response:
            return "Unknown"

        data = response.json()
        access_level = data.get("access_level")
        return access_level_map.get(access_level, "Unknown")

    @copydoc(GitAPI.get_pr_comments)
    def get_pr_comments(self, url, username, comment_re):
        data = self.get_all_pages(url)
        comments = []
        if not self._bad_response and data:
            for c in data:
                if c["author"]["username"] != username:
                    continue
                if re.search(comment_re, c["body"]):
                    c["url"] = "%s/%s" % (url, c["id"])
                    comments.append(c)
        return comments

    @copydoc(GitAPI.remove_pr_comment)
    def remove_pr_comment(self, comment):
        if not self._update_remote:
            return

        url = comment.get("url")
        self.delete(url)
        if not self._bad_response:
            logger.info("Removed comment: %s" % url)

    @copydoc(GitAPI.edit_pr_comment)
    def edit_pr_comment(self, comment, msg):
        if not self._update_remote:
            return

        url = comment.get("url")
        self.put(url, data={"body": msg})
        if not self._bad_response:
            logger.info("Edited PR comment: %s" % url)

    @copydoc(GitAPI.is_member)
    def is_member(self, team, user):
        if user.name == team:
            return True
        return self._is_group_member(team, user.name)

    @copydoc(GitAPI.get_open_prs)
    def get_open_prs(self, owner, repo):
        path_with_namespace = '%s/%s' % (owner, repo)
        url = "%s/merge_requests" % self._repo_url(path_with_namespace)
        params = {"state": "opened"}
        data = self.get_all_pages(url, params=params)
        if not self._bad_response and data is not None:
            open_prs = []
            for pr in data:
                open_prs.append({"number": pr["iid"], "title": pr["title"], "html_url": pr["web_url"]})
            return open_prs
        return None

    def _get_issues(self, path_with_namespace, title):
        """
        Get a list of open issues owned by the authenticated user that have the given title
        """
        url = "%s/issues" % self._repo_url(path_with_namespace)
        params = {"state": "opened", "scope": "created-by-me", "search": title}
        data = self.get_all_pages(url, params=params)
        matched_issues = []
        if not self._bad_response and data:
            for i in data:
                if i["title"] == title:
                    matched_issues.append(i)
        return matched_issues

    def _create_issue(self, path_with_namespace, title, body):
        """
        Create an issue on a repo with the given title and body
        """
        url = "%s/issues" % self._repo_url(path_with_namespace)
        post_data = {"title": title, "description": body}
        data = self.post(url, data=post_data)
        if not self._bad_response and data:
            logger.info("Created issue '%s': %s" % (title, data.json().get("web_url")))

    def _edit_issue(self, path_with_namespace, issue_id, title, body):
        """
        Modify the given issue on a repo with the given title and body
        """
        url = "%s/issues/%s" % (self._repo_url(path_with_namespace), issue_id)
        post_data = {"title": title, "description": body}
        data = self.put(url, data=post_data)
        if not self._bad_response and data:
            logger.info("Updated issue '%s': %s" % (title, data.json().get("web_url")))

    @copydoc(GitAPI.create_or_update_issue)
    def create_or_update_issue(self, owner, repo, title, body, new_comment):
        path_with_namespace = '%s/%s' % (owner, repo)
        if not self._update_remote:
            return
        existing_issues = self._get_issues(path_with_namespace, title)
        if existing_issues:
            issue_id = existing_issues[-1]["iid"]
            if new_comment:
                url = "%s/issues/%s/notes" % (self._repo_url(path_with_namespace), issue_id)
                self.pr_comment(url, body)
            else:
                self._edit_issue(path_with_namespace, issue_id, title, body)
        else:
            self._create_issue(path_with_namespace, title, body)

    @copydoc(GitAPI.pr_review_comment)
    def pr_review_comment(self, url, sha, filepath, position, msg):
        self._add_error("GitLab function not implemented: pr_review_comment")

    @copydoc(GitAPI.add_pr_label)
    def add_pr_label(self, repo, pr_num, label_name):
        self._add_error("GitLab function not implemented: add_pr_label")

    @copydoc(GitAPI.remove_pr_label)
    def remove_pr_label(self, repo, pr_num, label_name):
        self._add_error("GitLab function not implemented: remove_pr_label")

    @copydoc(GitAPI.automerge)
    def automerge(self, repo, pr_num):
        return False
