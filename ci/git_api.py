
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
import abc

class GitException(Exception):
    pass

import logging
import json
import requests
from requests.packages.urllib3.exceptions import InsecureRequestWarning
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)
logger = logging.getLogger('ci')

def copydoc(fromfunc, sep="\n"):
    """
    Decorator: Copy the docstring of `fromfunc`
    """
    def _decorator(func):
        sourcedoc = fromfunc.__doc__
        if func.__doc__ == None:
            func.__doc__ = sourcedoc
        else:
            func.__doc__ = sep.join([sourcedoc, func.__doc__])
        return func
    return _decorator

class GitAPI(object):
    __metaclass__ = abc.ABCMeta
    PENDING = 0
    ERROR = 1
    SUCCESS = 2
    FAILURE = 3
    RUNNING = 4
    CANCELED = 5

    STATUS_JOB_STARTED = 0
    STATUS_JOB_COMPLETE = 1
    STATUS_START_RUNNING = 2
    STATUS_CONTINUE_RUNNING = 3

    def __init__(self, config, access_user=None, token=None):
        super(GitAPI, self).__init__()
        self._config = config
        self._access_user = access_user
        self._token = token
        self._request_timeout = config.get("request_timeout", 5)
        self._install_webhook = config.get("install_webhook", False)
        self._update_remote = config.get("remote_update", False)
        self._remove_pr_labels = config.get("remove_pr_label_prefix", [])
        self._ssl_cert = config.get("ssl_cert", True)
        self._civet_url = config.get("civet_base_url", "")
        self._headers = {"User-Agent": "INL-CIVET/1.0 (+https://github.com/idaholab/civet)"}
        self._errors = []
        self._per_page = 50
        self._per_page_key = "per_page"
        self._default_params = {}
        self._get_params = {}
        self._bad_response = False
        self._session = None

    def _timeout(self, timeout):
        """
        Utility function to get the timeout value used in requests
        """
        if timeout is None:
            return self._request_timeout
        return timeout

    def _response_to_str(self, response):
        return "Status code: %s\nReason: %s\nJSON response:\n%s" % \
            (response.status_code, response.reason, self._format_json(response.json()))

    def _format_json(self, data):
        return json.dumps(data, indent=2)

    def _params(self, params, get=False):
        """
        Concatenates all the available parameters into a single dictionary
        """
        if params is None:
            return self._default_params

        if isinstance(params, dict):
            params.update(self._default_params)
            if get:
                params.update(self._get_params)
        return params

    def errors(self):
        return self._errors

    def _response_exception(self, url, method, e, data=None, params=None):
        data_str = ""
        if not data:
            data_str = "Sent data:\n%s\n" % self._format_json(data)
        param_str = ""
        if not params:
            param_str = "Sent params:\n%s\n" % self._format_json(params)
        msg = "Response exception:\nURL: %s\nMETHOD: %s\n%s%sError: %s" % (
                url, method, param_str, data_str, e)
        self._add_error(msg)
        self._bad_response = True

    def _add_error(self, err_str, log=True):
        """
        Adds an error string to the internal list of errors and log it.
        """
        self._errors.append(err_str)
        if log:
            logger.warning(err_str)

    def _check_response(self, response, params={}, data={}, log=True):
        try:
            response.raise_for_status()
        except Exception as e:
            params_str = ""
            if params:
                params_str = "Params:\n%s\n" % self._format_json(params)
            data_str = ""
            if data:
                data_str = "Data:\n%s\n" % self._format_json(data)
            headers = ""
            if self._headers:
                 headers = "Headers:\n%s\n" % self._format_json(self._headers)
            self._add_error("Bad response %s\nURL: %s\nMETHOD: %s\n%s%s%s%s\n%s\n%s"
                    % ("-"*50,
                        response.request.url,
                        response.request.method,
                        params_str,
                        data_str,
                        headers,
                        self._response_to_str(response),
                        e,
                        "-"*50),
                    log)
            self._bad_response = True
        return response

    def get(self, url, params=None, timeout=None, log=True):
        """
        Get the URL.
        Input:
            url[str]: URL to get
            params[dict]: Dictionary of extra parameters to send in the request
            timeout[int]: Specify a timeout other than the default.
        Return:
            requests.Reponse or None if there was a requests exception
        """
        self._bad_response = False
        try:
            timeout = self._timeout(timeout)
            params = self._params(params, True)
            response = self._session.get(url,
                    params=params, timeout=timeout, headers=self._headers, verify=self._ssl_cert)
        except Exception as e:
            return self._response_exception(url, "GET", e, params=params)

        return self._check_response(response, params=params, log=log)

    def post(self, url, params=None, data=None, timeout=None, log=True):
        """
        Post to a URL.
        Input:
            url[str]: URL to POST to.
            data[dict]: Dictionary of data to post
            timeout[int]: Specify a timeout other than the default.
        Return:
            requests.Reponse or None if there was a requests exception
        """
        self._bad_response = False
        try:
            timeout = self._timeout(timeout)
            params = self._params(params)
            response = self._session.post(url,
                    params=params,
                    json=data,
                    timeout=timeout,
                    headers=self._headers,
                    verify=self._ssl_cert)
        except Exception as e:
            return self._response_exception(url, "POST", e, data=data, params=params)

        return self._check_response(response, params=params, data=data, log=log)

    def patch(self, url, params=None, data=None, timeout=None, log=True):
        """
        Patch a URL.
        Input:
            url[str]: URL to PATCH
            timeout[int]: Specify a timeout other than the default.
        Return:
            requests.Reponse or None if there was any problems
        """
        self._bad_response = False
        params = self._params(params)
        try:
            timeout = self._timeout(timeout)
            response = self._session.patch(url,
                    params=params,
                    json=data,
                    timeout=timeout,
                    headers=self._headers,
                    verify=self._ssl_cert)
        except Exception as e:
            return self._response_exception(url, "PATCH", e, data=data, params=params)

        return self._check_response(response, params, data, log)

    def put(self, url, params=None, data=None, timeout=None, log=True):
        """
        Do a Put on a URL.
        Input:
            url[str]: URL to PATCH
            timeout[int]: Specify a timeout other than the default.
        Return:
            requests.Reponse or None if there was any problems
        """
        self._bad_response = False
        params = self._params(params)
        try:
            timeout = self._timeout(timeout)
            response = self._session.put(url,
                    params=params,
                    json=data,
                    timeout=timeout,
                    headers=self._headers,
                    verify=self._ssl_cert)
        except Exception as e:
            return self._response_exception(url, "PUT", e, data=data, params=params)

        return self._check_response(response, params, data, log)

    def delete(self, url, timeout=None, log=True):
        """
        Delete a URL.
        Input:
            url[str]: URL to DELETE
            timeout[int]: Specify a timeout other than the default.
        Return:
            requests.Reponse or None if there was any problems
        """
        self._bad_response = False
        try:
            timeout = self._timeout(timeout)
            response = self._session.delete(url,
                    params=self._default_params,
                    timeout=timeout,
                    headers=self._headers,
                    verify=self._ssl_cert)
        except Exception as e:
            return self._response_exception(url, "DELETE", e, params=self._default_params)

        return self._check_response(response, self._default_params, log=log)

    def get_all_pages(self, url, params=None, timeout=None, log=True):
        """
        Get all the pages for a URL by following the "next" links on a response.
        Input:
            url[str]: URL to get
            params[dict]: Dictionary of extra parameters to send in the request
            timeout[int]: Specify a timeout other than the default.
        Return:
            list: List ofor None if there was any problems
        """
        if params is None:
            params = {}
        params[self._per_page_key] = self._per_page
        response = self.get(url, params=params, timeout=timeout, log=log)
        if response is None or self._bad_response:
            return None

        all_json = response.json()
        try:
            while 'next' in response.links:
                response = self.get(response.links["next"]["url"],
                        params=params, timeout=timeout, log=log)
                if not self._bad_response and response:
                    all_json.extend(response.json())
                else:
                    break
        except Exception as e:
            self._add_error("Error getting multiple pages at %s\nSent data:\n%s\nError: %s" % (
                url, self._format_json(params), e), log)
        return all_json

    @abc.abstractmethod
    def sign_in_url(self):
        """
        Gets the URL to allow the user to sign in.
        Return:
          str: URL
        """

    @abc.abstractmethod
    def get_all_repos(self, owner):
        """
        Get a list of repositories the user has access to
        Input:
          owner[str]: user to check against
        Return:
          list[str]: Each entry is "<owner>/<repo name>"
        """

    @abc.abstractmethod
    def get_repos(self, session):
        """
        Get a list of repositories that the signed in user has access to.
        Input:
          session[HttpRequest.session]: session of the request. Used as a cache of the repositories.
        Return:
          list[str]: Each entry is "<owner>/<repo name>"
        """

    @abc.abstractmethod
    def get_branches(self, owner, repo):
        """
        Get a list of branches for a repository
        Input:
          owner[str]: owner of the repository
          repo[str]: name of the repository
        Return:
          list[str]: Each entry is the name of a branch
        """

    @abc.abstractmethod
    def update_pr_status(self, base, head, state, event_url, description, context, job_stage):
        """
        Update the PR status.
        Input:
          base[models.Commit]: Original commit
          head[models.Commit]: New commit
          state[int]: One of the states defined as class variables above
          event_url[str]: URL back to the moosebuild page
          descriptionstr]: Description of the update
          context[str]: Context for the update
          job_stage[int]: One of the STATUS_* flags
        """

    @abc.abstractmethod
    def is_collaborator(self, user, repo):
        """
        Check to see if the signed in user is a collaborator on a repo
        Input:
          user[models.GitUser]: User to check against
          repo[models.Repository]: Repository to check against
        Return:
          bool: True if user is a collaborator on repo, False otherwise
        """
    @abc.abstractmethod
    def pr_review_comment(self, url, sha, filepath, position, msg):
        """
        Leave a review comment on a PR for a specific hash, on a specific position of a file
        Input:
          url[str]: URL to post the message to
          sha[str]: SHA of the PR branch to attach the message to
          filepath[str]: Filepath of the file to attach the message to
          position[str]: Position in the diff to attach the message to
          msg[str]: Comment
        """

    @abc.abstractmethod
    def pr_comment(self, url, msg):
        """
        Leave a comment on a PR
        Input:
          url[str]: URL to post the message to
          msg[str]: Comment
        """

    @abc.abstractmethod
    def last_sha(self, owner, repo, branch):
        """
        Get the latest SHA for a branch
        Input:
          owner[str]: owner of the repository
          repo[str]: name of the repository
          branch[str]: name of the branch
        Return:
          str: Last SHA of the branch or None if there was a problem
        """

    @abc.abstractmethod
    def install_webhooks(self, user, repo):
        """
        Updates the webhook for this server on GitHub.
        Input:
          user[models.GitUser]: the user trying to update the web hooks.
          repo[models.Repository]: the repository to set the web hook on.
        Raises:
          GitException if there are any errors.
        """

    @abc.abstractmethod
    def repo_html_url(self, owner, repo):
        """
        Gets a URL to the repository
        Input:
          owner[str]: Owner of the repo
          repo[str]: Name of the repo
        Return:
          str: URL on the gitserver to the repo
        """

    @abc.abstractmethod
    def branch_html_url(self, owner, repo, branch):
        """
        Gets a URL to the branch
        Input:
          owner[str]: Owner of the repo
          repo[str]: Name of the repo
          branch[str]: Name of the branch
        Return:
          str: URL on the gitserver to the branch
        """

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

    @abc.abstractmethod
    def add_pr_label(self, repo, pr_num, label_name):
        """
        Add a label to a PR
        Input:
            repo[models.Repository]: Repository of the PR
            pr_num[int]: PR number
            label_name[str]: Text of the label
        """

    @abc.abstractmethod
    def remove_pr_label(self, repo, pr_num, label_name):
        """
        Remove a label from a PR
        Input:
            builduser[models.GitUser]: User that will actually attach the label
            repo[models.Repository]: Repository of the PR
            pr_num[int]: PR number
            label_name[str]: Text of the label
        """

    @abc.abstractmethod
    def get_pr_comments(self, url, username, comment_re):
        """
        Get a list of comments authoried by a user that matches a regular expression.
        Input:
          url[str]: URL to get comments from
          username[str]: Username that authored comments
          comment_re[str]: Regular expression to match against the body of comments
        Return:
            list[dict]: Comments
        """

    @abc.abstractmethod
    def remove_pr_comment(self, comment):
        """
        Remove a comment on a PR
        Input:
          comment[dict]: Git server information as returned by get_pr_comments()
        """

    @abc.abstractmethod
    def edit_pr_comment(self, comment, msg):
        """
        Edit an existing comment on a PR
        Input:
          comment[dict]: Git server information as returned by get_pr_comments()
          msg[str]: New comment body
        """

    @abc.abstractmethod
    def is_member(self, team, user):
        """
        Checks to see if a user is a member of a team/org/group
        Input:
          team[str]: Name of the team/org/group
          user[models.GitUser]: User to check
        """

    @abc.abstractmethod
    def get_open_prs(self, owner, repo):
        """
        Get a list of open PRs for a repo
        Input:
          owner[str]: owner name
          repo[str]: repo name
        Return:
            list[dict]: None can be returned on error.
            Each dict will have the following key/value pairs:
                number[int]: PR number
                title[str]: Title of the PR
                html_url[str]: URL to the PR
        """

    @abc.abstractmethod
    def create_or_update_issue(self, owenr, repo, title, body, new_comment):
        """
        If an open issue with the given title exists, then update it.
        Otherwise create a new issue.
        The issue will be created by the user that created the GitAPI.
        Input:
          owner[str]: owner of the repository to create/update the issue on
          repo[str]: repository to create/update the issue on
          title[str]: title of issue
          body[str]: body of issue
          new_comment[bool]: If true, create a new comment. Else just update the issue body
        """

    @abc.abstractmethod
    def automerge(self, repo, pr_num):
        """
        See if a PR can be automerged.
        Input:
          repo[models.Repository]: repository to create/update the issue on
          pr_num[str]: Number of the PR
        """
