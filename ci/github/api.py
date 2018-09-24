
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
from ci.git_api import GitAPI, GitException, copydoc
import requests
import re
try:
    from urllib.parse import urljoin
except ImportError:
    from urlparse import urljoin

logger = logging.getLogger('ci')

class GitHubAPI(GitAPI):
    STATUS = ((GitAPI.PENDING, "pending"),
        (GitAPI.ERROR, "error"),
        (GitAPI.SUCCESS, "success"),
        (GitAPI.FAILURE, "failure"),
        (GitAPI.RUNNING, "pending"),
        (GitAPI.CANCELED, "error"),
        )

    def __init__(self, config, access_user=None, token=None):
        super(GitHubAPI, self).__init__(config, access_user=access_user,  token=token)
        self._api_url = config.get("api_url", "https://api.github.com")
        self._github_url = config.get("html_url", "https://github.com")
        self._hostname = config.get("hostname", "github.com")
        self._prefix = "%s_" % self._hostname
        self._repos_key = "%s_repos" % self._prefix
        self._org_repos_key = "%s_org_repos" % self._prefix
        self._headers["Accept"] = "application/vnd.github.v3+json"

        if self._access_user is not None:
            self._session = self._access_user.start_session()
        elif self._token is not None:
            self._headers["Authorization"] = "token %s" % self._token
            self._session = requests
        else:
            # No authorization, just straight requests
            self._session = requests

    @copydoc(GitAPI.sign_in_url)
    def sign_in_url(self):
        return reverse('ci:github:sign_in', args=[self._hostname])

    @copydoc(GitAPI.branch_html_url)
    def branch_html_url(self, owner, repo, branch):
        return "%s/tree/%s" % (self.repo_html_url(owner, repo), branch)

    @copydoc(GitAPI.repo_html_url)
    def repo_html_url(self, owner, repo):
        return "%s/%s/%s" %(self._github_url, owner, repo)

    @copydoc(GitAPI.commit_html_url)
    def commit_html_url(self, owner, repo, sha):
        return "%s/commits/%s" % (self.repo_html_url(owner, repo), sha)

    def _commit_comment_url(self, owner, repo, sha):
        """
        API URL to get a list of commits for a SHA.
        Typically used for the comment URL on a push event.
        """
        return "%s/repos/%s/%s/commits/%s/comments" % (self._api_url, owner, repo, sha)

    def _status_str(self, status):
        """
        Used to convert a GitAPI status into a string that GitHub wants.
        """
        for status_pair in self.STATUS:
            if status == status_pair[0]:
                return status_pair[1]
        return None

    @copydoc(GitAPI.get_all_repos)
    def get_all_repos(self, username):
        repos = self._get_user_repos()
        repos.extend(self._get_user_org_repos())
        repos.sort()
        return repos

    def _get_user_repos(self):
        """
        Gets a list of repos the user owns or is a collaborator on.
        """
        url = "%s/user/repos" % self._api_url
        data = {"affiliation": ["owner", "collaborator"]}
        repo_data = self.get_all_pages(url, data)
        owner_repo = []
        if repo_data:
            for repo in repo_data:
                owner_repo.append("%s/%s" % (repo['owner']['login'], repo['name']))
            owner_repo.sort()
        return owner_repo

    @copydoc(GitAPI.get_repos)
    def get_repos(self, session):
        if self._repos_key in session:
            return session[self._repos_key]
        owner_repo = self._get_user_repos()
        session[self._repos_key] = owner_repo
        return owner_repo

    @copydoc(GitAPI.get_branches)
    def get_branches(self, owner, repo):
        url = "%s/repos/%s/%s/branches" % (self._api_url, owner, repo)
        data = self.get_all_pages(url)
        branches = []
        if data:
            for branch in data:
                branches.append(branch['name'])
        branches.sort()
        return branches

    def _get_user_org_repos(self):
        """
        Get a list of organizations that the user is a member of.
        """
        url = "%s/user/repos" % self._api_url
        data = {"affiliation": "organization_member"}
        repo_data = self.get_all_pages(url, data)
        org_repo = []
        if repo_data:
            for repo in repo_data:
                org_repo.append("%s/%s" % (repo['owner']['login'], repo['name']))
            org_repo.sort()
        return org_repo

    @copydoc(GitAPI.update_pr_status)
    def update_pr_status(self, base, head, state, event_url, description, context, job_stage):
        self._update_pr_status(base.user().name, base.repo().name, head.sha, state, event_url, description, context)

    def _update_pr_status(self, owner, repo, sha, state, event_url, description, context):
        """
        Utility function that implements GitAPI.update_pr_status
        """

        if not self._update_remote:
            return

        data = {
            'state': self._status_str(state),
            'target_url': event_url,
            'description': description,
            'context': context,
            }
        url = "%s/repos/%s/%s/statuses/%s" % (self._api_url, owner, repo, sha)
        timeout=None
        if state in [self.RUNNING, self.PENDING]:
            # decrease the timeout since it is not a big deal if these don't get set
            timeout = 2

        self.post(url, data=data, timeout=timeout)
        if not self._bad_response:
            logger.info("Set pr status %s:\nSent Data:\n%s" % (url, self._format_json(data)))

    def _remove_pr_todo_labels(self, owner, repo, pr_num):
        """
        Removes all labels on a PR with the labels that start with a certain prefix
        Input:
          owner[str]: name of the owner of the repo
          repo[str]: name of the repository
          pr_num[int]: PR number
        """
        if not self._update_remote:
            return

        url = "%s/repos/%s/%s/issues/%s/labels" % (self._api_url, owner, repo, pr_num)
        # First get a list of all labels
        data = self.get_all_pages(url)
        if not data:
            return

        # We could filter out the unwanted labels and then POST the new list
        # but I don't like the message that appears on GitHub.
        # Instead, delete each one. This should be fine since there won't
        # be many of these.
        for label in data:
            for remove_label in self._remove_pr_labels:
                if label["name"].startswith(remove_label):
                    new_url = "%s/%s" % (url, label["name"])
                    response = self.delete(new_url)
                    if response is not None:
                        logger.info("%s/%s #%s: Removed label '%s'" % (owner, repo, pr_num, label["name"]))
                    break

    @copydoc(GitAPI.remove_pr_label)
    def remove_pr_label(self, repo, pr_num, label_name):
        self._remove_pr_label(repo.user.name, repo.name, pr_num, label_name)

    def _remove_pr_label(self, owner, repo, pr_num, label_name):
        """
        Implements GitAPI.remove_pr_label
        """
        if not self._update_remote:
            return

        prefix = "%s/%s #%s:" % (owner, repo, pr_num)
        if not label_name:
            logger.info("%s Not removing empty label" % prefix)
            return

        url = "%s/repos/%s/%s/issues/%s/labels/%s" % (self._api_url, owner, repo, pr_num, label_name)
        response = self.delete(url, log=False)
        if not response or response.status_code == 404:
            # if we get this then the label probably isn't on the PR
            logger.info("%s Label '%s' was not found" % (prefix, label_name))
            return

        try:
            response.raise_for_status()
            logger.info("%s Removed label '%s'" % (prefix, label_name))
        except Exception as e:
            msg = "%s Problem occured while removing label '%s'\nURL: %s\nError: %s" \
                % (prefix, label_name, url, e)
            self._add_error(msg)

    @copydoc(GitAPI.add_pr_label)
    def add_pr_label(self, repo, pr_num, label_name):
        self._add_pr_label(repo.user.name, repo.name, pr_num, label_name)

    def _add_pr_label(self, owner, repo, pr_num, label_name):
        """
        Implements GitAPI.add_pr_label
        """
        if not self._update_remote:
            return

        prefix = "%s/%s #%s:" % (owner, repo, pr_num)
        if not label_name:
            logger.info("%s Not adding empty label" % prefix)
            return

        url = "%s/repos/%s/%s/issues/%s/labels" % (self._api_url, owner, repo, pr_num)
        response = self.post(url, data=[label_name])
        if not self._bad_response and response is not None:
            logger.info("%s Added label '%s'" % (prefix, label_name))

    @copydoc(GitAPI.is_collaborator)
    def is_collaborator(self, user, repo):
        return self._is_collaborator(user.name, repo.user.name, repo.name)

    def _is_collaborator(self, user, owner, repo):
        """
        Implements GitAPI.is_collaborator
        """
        if owner == user:
            # user is the owner
            return True

        url = "%s/repos/%s/%s/collaborators/%s" % (self._api_url, owner, repo, user)
        response = self.get(url, log=False)
        if response is None:
            self._add_error("Error occurred getting URL %s" % url)
            return False

        prefix = "%s/%s:" % (owner, repo)
        # on success a 204 no content
        if response.status_code == 403:
            logger.info('%s User "%s" does not have permission to check collaborators' % (prefix, user))
            return False
        elif response.status_code == 404:
            logger.info('%s User "%s" is NOT a collaborator' % (prefix, user))
            return False
        elif response.status_code == 204:
            logger.info('%s User "%s" is a collaborator' % (prefix, user))
            return True
        else:
            self._add_error('%s Unknown response on collaborator check for user "%s"\n%s' %
                    (prefix, user, self._response_to_str(response)))
        return False

    @copydoc(GitAPI.pr_comment)
    def pr_comment(self, url, msg):
        if not self._update_remote:
            return

        comment = {'body': msg}
        self.post(url, data=comment)

    @copydoc(GitAPI.pr_review_comment)
    def pr_review_comment(self, url, sha, filepath, position, msg):
        if not self._update_remote:
            return

        comment = {'body': msg,
            "commit_id": sha,
            "path": filepath,
            "position": int(position),
            }
        self.post(url, data=comment)

    @copydoc(GitAPI.last_sha)
    def last_sha(self, owner, repo, branch):
        url = "%s/repos/%s/%s/branches/%s" % (self._api_url, owner, repo, branch)
        response = self.get(url)
        if not self._bad_response:
            data = response.json()
            if data and "commit" in data:
                return data['commit']['sha']
        self._add_error("Failed to get last SHA for %s/%s:%s" % (owner, repo, branch))

    def _tag_sha(self, owner, repo, tag):
        """
        Get the SHA for a tag
        Input:
          owner[str]: owner of the repository
          repo[str]: name of the repository
          tag[str]: name of the tag
        Return:
          SHA of the tag or None if there was a problem
        """
        url = "%s/repos/%s/%s/tags" % (self._api_url, owner, repo)
        data = self.get_all_pages(url)
        if data:
            for t in data:
                if t["name"] == tag:
                    return t["commit"]["sha"]
        self._add_error('Failed to find tag "%s" in %s.' % (tag, url))

    @copydoc(GitAPI.install_webhooks)
    def install_webhooks(self, user, repo):
        self._install_webhooks(user.name, user.build_key, repo.user.name, repo.name)

    def _install_webhooks(self, user, user_build_key, owner, repo):
        """
        Implements GitAPI.install_webhooks
        """
        if not self._install_webhook:
            return

        hook_url = '%s/repos/%s/%s/hooks' % (self._api_url, owner, repo)
        callback_url = urljoin(self._civet_url, reverse('ci:github:webhook', args=[user_build_key]))
        data = self.get_all_pages(hook_url)
        if self._bad_response or data is None:
            err = 'Failed to access webhook to %s/%s for user %s' % (owner, repo, user)
            self._add_error(err)
            raise GitException(err)

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
        response = self.post(hook_url, data=add_hook)
        data = response.json()
        if self._bad_response or "errors" in data:
            raise GitException(data['errors'])

        logger.info('%s/%s: Added webhook for user %s' % (owner, repo, user))

    def _get_pr_changed_files(self, owner, repo, pr_num):
        """
        Gets a list of changed files in this PR.
        Input:
          owner[str]: name of the owner of the repo
          repo[str]: name of the repository
          pr_num[int]: PR number
        Return:
          list[str]: Filenames that have changed in the PR
        """
        url = "%s/repos/%s/%s/pulls/%s/files" % (self._api_url, owner, repo, pr_num)

        data = self.get_all_pages(url)
        filenames = []
        if data and not self._bad_response:
            for f in data:
                if "filename" in f:
                    filenames.append(f["filename"])
            filenames.sort()
        if not filenames:
            self._add_error("Didn't read any PR changed files at URL: %s\nData: %s" % (url, data))
        return filenames

    @copydoc(GitAPI.get_pr_comments)
    def get_pr_comments(self, url, username, comment_re):
        data = self.get_all_pages(url)
        comments = []
        if not self._bad_response and data:
            for c in data:
                if c["user"]["login"] != username:
                    continue
                if re.search(comment_re, c["body"]):
                    comments.append(c)
        return comments

    @copydoc(GitAPI.remove_pr_comment)
    def remove_pr_comment(self, comment):
        if not self._update_remote:
            return

        del_url = comment.get("url")
        response = self.delete(del_url)
        if not self._bad_response and response:
            logger.info("Removed comment: %s" % del_url)

    @copydoc(GitAPI.edit_pr_comment)
    def edit_pr_comment(self, comment, msg):
        if not self._update_remote:
            return

        edit_url = comment.get("url")
        response = self.patch(edit_url, data={"body": msg})
        if not self._bad_response and response:
            logger.info("Edited PR comment: %s" % edit_url)

    def _is_org_member(self, org):
        """
        Checks to see if the user is a member of an organization.
        Input:
            org[str]: Name of the organization to check
        Return:
            bool
        """
        url = "%s/user/orgs" % self._api_url
        data = self.get_all_pages(url)
        if not self._bad_response and data:
            for org_data in data:
                if org_data["login"] == org:
                    return True
        return False

    def _is_team_member(self, team_id, username):
        """
        Checks to see if a user is a member of the team.
        Input:
            team_id[int]: ID of the team to check
            username[str]: The user to check
        Return:
            bool
        """
        url = "%s/teams/%s/memberships/%s" % (self._api_url, team_id, username)
        response = self.get(url, log=False)
        if not self._bad_response and response:
            data = response.json()
            if data['state'] == 'active':
                return True
        return False

    def _get_team_id(self, owner, team):
        """
        Gets the internal team id of a team.
        """
        url = "%s/orgs/%s/teams" % (self._api_url, owner)
        response = self.get(url)
        if not self._bad_response and response:
            data = response.json()
            for team_data in data:
                if team_data["name"] == team:
                    return team_data["id"]
        self._add_error("Failed to find team '%s' at URL: %s" % (team, url))

    @copydoc(GitAPI.is_member)
    def is_member(self, team, user):
        paths = team.split("/")
        if len(paths) == 1:
            # No / so should be a user or organization
            if user.name == team:
                return True

            # Try the call using the users credentials
            api = GitHubAPI(self._config, access_user=user)
            ret = api._is_org_member(team)
            if ret:
                logger.info('"%s" IS a member of organization "%s"' % (user, team))
            else:
                logger.info('"%s" is NOT a member of organization "%s"' % (user, team))
            return ret
        elif len(paths) == 2:
            # Must be a team in the form <org>/<team name>
            team_id = self._get_team_id(paths[0], paths[1])
            if team_id is not None:
                ret = self._is_team_member(team_id, user.name)
                if ret:
                    logger.info('"%s" IS a member of team "%s"' % (user, team))
                else:
                    logger.info('"%s" is NOT a member of team "%s"' % (user, team))
                return ret
        self._add_error("Failed to check if '%s' is a member of '%s': Bad team name" % (user, team))
        return False

    @copydoc(GitAPI.get_open_prs)
    def get_open_prs(self, owner, repo):
        url = "%s/repos/%s/%s/pulls" % (self._api_url, owner, repo)
        params = {"state": "open"}
        data = self.get_all_pages(url, params=params)
        open_prs = []
        if not self._bad_response and data is not None:
            for pr in data:
                open_prs.append({"number": pr["number"], "title": pr["title"], "html_url": pr["html_url"]})
            return open_prs
        return None

    def _get_issues(self, user, owner, repo, title):
        """
        Get a list of open issues owned by the user that have the given title
        """
        url = "%s/repos/%s/%s/issues" % (self._api_url, owner, repo)
        params = {"state": "open", "creator": user}
        data = self.get_all_pages(url, params=params)
        matched_issues = []
        if not self._bad_response and data:
            for i in data:
                if i["title"] == title:
                    matched_issues.append(i)
        return matched_issues

    def _create_issue(self, owner, repo, title, body):
        """
        Create an issue on a repo with the given title and body
        """
        url = "%s/repos/%s/%s/issues" % (self._api_url, owner, repo)
        post_data = {"title": title, "body": body}
        data = self.post(url, data=post_data)
        if not self._bad_response and data:
            logger.info("Created issue \"%s\": %s" % (title, data.json().get("html_url")))

    def _edit_issue(self, owner, repo, issue_id, title, body):
        """
        Modify the given issue on a repo with the given title and body
        """
        url = "%s/repos/%s/%s/issues/%s" % (self._api_url, owner, repo, issue_id)
        post_data = {"title": title, "body": body}
        data = self.patch(url, data=post_data)
        if not self._bad_response and data:
            logger.info("Updated issue \"%s\": %s" % (title, data.json().get("html_url")))

    @copydoc(GitAPI.create_or_update_issue)
    def create_or_update_issue(self, owner, repo, title, body, new_comment):
        if not self._access_user or not self._update_remote:
            return
        username = self._access_user.name
        existing_issues = self._get_issues(username, owner, repo, title)
        if existing_issues:
            if new_comment:
                self.pr_comment(existing_issues[-1]["comments_url"], body)
            else:
                issue_id = existing_issues[-1]["number"]
                self._edit_issue(owner, repo, issue_id, title, body)
        else:
            self._create_issue(owner, repo, title, body)

    @copydoc(GitAPI.automerge)
    def automerge(self, repo, pr_num):
        if not self._update_remote:
            return False

        auto_merge_label = repo.auto_merge_label()
        auto_merge_require_review = repo.auto_merge_require_review()
        if not auto_merge_label:
            logger.info("%s:%s: No auto merging configured" % (self._hostname, repo))
            return False

        repo_name = repo.name
        owner = repo.user.name

        url = "%s/repos/%s/%s/pulls/%s" % (self._api_url, owner, repo_name, pr_num)
        prefix = "%s:%s/%s #%s:" % (self._hostname, owner, repo_name, pr_num)
        pr_info = self.get_all_pages(url)
        if pr_info is None or self._bad_response:
            logger.info("%s Failed to get info" % prefix)
            return False

        all_labels = [label["name"] for label in pr_info["labels"]]
        if auto_merge_label not in all_labels:
            logger.info("%s Auto merge label not on PR" % prefix)
            return False
        pr_head = pr_info["head"]["sha"]

        if auto_merge_require_review:
            url = "%s/repos/%s/%s/pulls/%s/reviews" % (self._api_url, owner, repo_name, pr_num)
            reviews = self.get_all_pages(url)
            if not reviews or self._bad_response:
                logger.info("%s No reviews, not auto merging" % prefix)
                return False
            is_approved = False
            changes_requested = False
            for review in reviews:
                if review["commit_id"] == pr_head:
                    if review["state"] == "CHANGES_REQUESTED":
                        changes_requested = True
                    elif review["state"] == "APPROVED":
                        is_approved = True

            if not is_approved:
                logger.info("%s Not approved, not auto merging" % prefix)
                return False
            if changes_requested:
                logger.info("%s Changes requested, not auto merging" % prefix)
                return False

        url = "%s/repos/%s/%s/pulls/%s/merge" % (self._api_url, owner, repo_name, pr_num)
        data = {"sha": pr_head}
        self.put(url, data=data)
        if self._bad_response:
            logger.info("%s Failed to auto merge" % prefix)
            return False
        else:
            logger.info("%s Auto merged" % prefix)
            return True
