
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

from __future__ import unicode_literals
from django.urls import reverse
import logging
import requests
from ci.git_api import GitAPI, GitException, copydoc

logger = logging.getLogger('ci')

class BitBucketAPI(GitAPI):
    STATUS = ((GitAPI.PENDING, "INPROGRESS"),
        (GitAPI.ERROR, "FAILED"),
        (GitAPI.SUCCESS, "SUCCESSFUL"),
        (GitAPI.FAILURE, "FAILED"),
        (GitAPI.RUNNING, "INPROGRESS"),
        (GitAPI.CANCELED, "STOPPED"),
        )

    def __init__(self, config, access_user=None, token=None):
        super(BitBucketAPI, self).__init__(config, access_user=access_user, token=token)
        self._api2_url = config.get("api2_url", "")
        self._api1_url = config.get("api1_url", "")
        self._bitbucket_url = config.get("html_url", "")
        self._hostname = config.get("hostname", "unknown_bitbucket")
        self._prefix = "%s_" % self._hostname
        self._repos_key = "%s_repos" % self._prefix
        self._org_repos_key = "%s_org_repos" % self._prefix
        self._user_key = "%s_user" % self._prefix
        self._per_page_key = "pagelen"

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
        return reverse('ci:bitbucket:sign_in', args=[self._hostname])

    def _repo_url(self, owner, repo):
        return "%s/repositories/%s/%s" % (self._api1_url, owner, repo)

    @copydoc(GitAPI.repo_html_url)
    def repo_html_url(self, owner, repo):
        return "%s/%s/%s" % (self._bitbucket_url, owner, repo)

    @copydoc(GitAPI.branch_html_url)
    def branch_html_url(self, owner, repo, branch):
        return "%s/branches/%s" % (self.repo_html_url(owner, repo), branch)

    @copydoc(GitAPI.commit_html_url)
    def commit_html_url(self, owner, repo, sha):
        return "%s/commits/%s" % (self.repo_html_url(owner, repo), sha)

    def _pr_comment_api_url(self, owner, repo, pr_id):
        return "%s/pullrequests/%s/comments" % (self._repo_url(owner, repo), pr_id)

    def _commit_comment_url(self, owner, repo, sha):
        return self.commit_html_url(owner, repo, sha)

    @copydoc(GitAPI.get_all_repos)
    def get_all_repos(self, owner):
        owner_repos, org_repos = self._get_user_repos(owner)
        owner_repos.extend(org_repos)
        return owner_repos

    def _get_user_repos(self, username):
        if not username:
            return [], []

        url = "%s/user/repositories" % (self._api1_url)
        data = self.get_all_pages(url)
        owner_repo = []
        org_repos = []
        if not self._bad_response and data:
            for repo in data:
                owner = repo["owner"]
                name = repo["name"]
                full_name = "%s/%s" % (owner, name)
                if owner == username:
                    owner_repo.append(full_name)
                else:
                    org_repos.append(full_name)
            org_repos.sort()
            owner_repo.sort()
        return owner_repo, org_repos

    @copydoc(GitAPI.get_repos)
    def get_repos(self, session):
        if self._repos_key in session and self._org_repos_key in session:
            return session[self._repos_key]

        user = session.get(self._user_key)
        owner_repos, org_repos = self._get_user_repos(user)
        session[self._org_repos_key] = org_repos
        session[self._repos_key] = owner_repos
        return owner_repos

    @copydoc(GitAPI.get_branches)
    def get_branches(self, owner, repo):
        url = "%s/branches" % (self._repo_url(owner, repo))
        data = self.get_all_pages(url)
        branches = []
        if not self._bad_response and data:
            branches = list(data.keys())
            branches.sort()
        return branches

    @copydoc(GitAPI.is_collaborator)
    def is_collaborator(self, user, repo):
        if repo.user == user:
            # user is the owner
            return True

        # now ask bitbucket
        url = "%s/repositories/%s" % (self._api2_url, repo.user.name)
        data = self.get_all_pages(url, params={'role': 'contributor'})
        if not self._bad_response and data and "values" in data:
            for repo_data in data['values']:
                if repo_data['name'] == repo.name:
                    logger.info('User "%s" IS a collaborator on %s' % (user, repo))
                    return True
        logger.info('User "%s" is NOT a collaborator on %s' % (user, repo))
        return False

    @copydoc(GitAPI.pr_comment)
    def pr_comment(self, url, msg):
        if not self._update_remote:
            return

        data = {'content': msg}
        self.post(url, data=data)

    @copydoc(GitAPI.last_sha)
    def last_sha(self, owner, repo, branch):
        url = "%s/branches" % (self._repo_url(owner, repo))
        data = self.get_all_pages(url)
        if not self._bad_response and data:
            branch_data = data.get(branch)
            if branch_data:
                return branch_data['raw_node']
        self._add_error("Failed to get branch information at %s." % url)

    @copydoc(GitAPI.install_webhooks)
    def install_webhooks(self, user, repo):
        if not self._install_webhook:
            return

        hook_url = '%s/repositories/%s/%s/hooks' % (self._api2_url, repo.user.name, repo.name)
        callback_url = "%s%s" % (self._civet_url, reverse('ci:bitbucket:webhook', args=[user.build_key]))
        data = self.get_all_pages(hook_url)
        if self._bad_response or data is None:
            err = 'Failed to access webhook to %s/%s for user %s' % (repo.user.name, repo, user)
            self._add_error(err)
            raise GitException(err)

        have_hook = False
        for hook in data['values']:
            if 'pullrequest:created' not in hook['events'] or 'repo:push' not in hook['events']:
                continue
            if hook['url'] == callback_url:
                have_hook = True
                break

        if have_hook:
            return

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
        response = self.post(hook_url, data=add_hook)
        if self._bad_response:
            logger.warning('Failed to add webhook: %s' % (self._response_to_str(response)))
            raise GitException(data)
        logger.info('Added webhook to %s for user %s' % (repo, user.name))


    @copydoc(GitAPI.get_open_prs)
    def get_open_prs(self, owner, repo):
        url = "%s/repositories/%s/%s/pullrequests" % (self._api2_url, owner, repo)
        params = {"state": "OPEN"}
        data = self.get_all_pages(url, params=params)
        if not self._bad_response and data is not None:
            open_prs = []
            for pr in data.get("values", []):
                open_prs.append({"number": pr["id"], "title": pr["title"], "html_url": pr["links"]["html"]})
            return open_prs
        return None

    @copydoc(GitAPI.update_pr_status)
    def update_pr_status(self, base, head, state, event_url, description, context, job_stage):
        self._add_error("FIXME: BitBucket function not implemented: update_pr_status")

    @copydoc(GitAPI.is_member)
    def is_member(self, team, user):
        self._add_error("FIXME: BitBucket function not implemented: is_member")
        return False

    @copydoc(GitAPI.add_pr_label)
    def add_pr_label(self, builduser, repo, pr_num, label_name):
        self._add_error("FIXME: BitBucket function not implemented: add_pr_label")

    @copydoc(GitAPI.remove_pr_label)
    def remove_pr_label(self, builduser, repo, pr_num, label_name):
        self._add_error("FIXME: BitBucket function not implemented: remove_pr_label")

    @copydoc(GitAPI.get_pr_comments)
    def get_pr_comments(self, url, username, comment_re):
        self._add_error("FIXME: BitBucket function not implemented: get_pr_comments")
        return []

    @copydoc(GitAPI.remove_pr_comment)
    def remove_pr_comment(self, comment):
        self._add_error("FIXME: BitBucket function not implemented: remove_pr_comment")

    @copydoc(GitAPI.edit_pr_comment)
    def edit_pr_comment(self, comment, msg):
        self._add_error("FIXME: BitBucket function not implemented: edit_pr_comment")

    @copydoc(GitAPI.pr_review_comment)
    def pr_review_comment(self, url, msg):
        self._add_error("FIXME: BitBucket function not implemented: pr_review_comment")

    @copydoc(GitAPI.create_or_update_issue)
    def create_or_update_issue(self, owner, repo, title, body):
        self._add_error("FIXME: BitBucket function not implemented: create_or_update_issue")
