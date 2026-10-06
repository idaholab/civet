# Copyright 2016-2025 Battelle Energy Alliance, LLC
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
from urllib.parse import quote, unquote, urlparse

logger = logging.getLogger("ci")


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


class ForbiddenException(Exception):
    """An exception thrown when a request is forbidden."""


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

    # Lowercase names of the request headers that carry credentials and
    # must never be logged
    SENSITIVE_HEADERS = (
        "authorization",
        "private-token",
        "proxy-authorization",
        "cookie",
    )

    def __init__(self, config, access_user=None, token=None):
        super(GitAPI, self).__init__()
        self._config = config
        self._access_user = access_user
        self._token = token
        self._request_timeout = config.get("request_timeout", 5)
        self._update_remote = config.get("remote_update", False)
        self._remove_pr_labels = config.get("remove_pr_label_prefix", [])
        self._ssl_cert = self._ssl_verify(config.get("ssl_cert", True))
        self._headers = {
            "User-Agent": "INL-CIVET/1.0 (+https://github.com/idaholab/civet)"
        }
        self._errors = []
        self._per_page = 50
        self._per_page_key = "per_page"
        self._default_params = {}
        self._get_params = {}
        self._bad_response = False
        self._session = None
        # Set by the subclasses; requests are only sent to this scheme and host
        self._api_url = None

    def _ssl_verify(self, ssl_cert):
        """
        Get the value to pass as "verify" to requests. Certificate
        verification can't be turned off; the "ssl_cert" setting can
        only be True or the path to a CA bundle.
        Input:
            ssl_cert: The "ssl_cert" value from the server config
        Return:
            The CA bundle path, or True to use the default CA bundle
        """
        if isinstance(ssl_cert, str) and ssl_cert:
            return ssl_cert
        if ssl_cert is not True:
            logger.warning(
                "Ignoring ssl_cert=%r; it must be True or the path to a CA "
                "bundle. Verifying certificates with the default CA bundle."
                % (ssl_cert,)
            )
        return True

    def _timeout(self, timeout):
        """
        Utility function to get the timeout value used in requests
        """
        if timeout is None:
            return self._request_timeout
        return timeout

    def _response_to_str(self, response):
        response_json = "INVALID JSON"
        try:
            response_json = self._format_json(response.json())
        except:
            pass
        return "Status code: %s\nReason: %s\nJSON response:\n%s" % (
            response.status_code,
            response.reason,
            response_json,
        )

    def _format_json(self, data):
        return json.dumps(data, indent=2)

    @staticmethod
    def _redacted_headers(headers):
        """
        Get a copy of the headers that is safe to log, with the values
        of any headers that carry credentials replaced.
        Input:
            headers[dict]: The request headers
        Return:
            dict: The headers with the credential values redacted
        """
        return {
            key: (
                "[REDACTED]" if str(key).lower() in GitAPI.SENSITIVE_HEADERS else value
            )
            for key, value in headers.items()
        }

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
            url,
            method,
            param_str,
            data_str,
            e,
        )
        self._add_error(msg)
        self._bad_response = True

    def _add_error(self, err_str, log=True):
        """
        Adds an error string to the internal list of errors and log it.
        """
        self._errors.append(err_str)
        if log:
            logger.warning(err_str)

    @staticmethod
    def _possibly_raise_forbidden(e: Exception, response: requests.Response):
        """Raise ForbiddenException if the exception is a 403 status."""
        assert isinstance(e, Exception)
        assert isinstance(response, requests.Response)

        if isinstance(e, requests.exceptions.HTTPError) and response.status_code == 403:
            raise ForbiddenException()

    def _check_response(
        self, response, params={}, data={}, log=True, raise_forbidden=False
    ):
        try:
            response.raise_for_status()
        except Exception as e:
            if raise_forbidden:
                self._possibly_raise_forbidden(e, response)

            params_str = ""
            if params:
                params_str = "Params:\n%s\n" % self._format_json(params)
            data_str = ""
            if data:
                data_str = "Data:\n%s\n" % self._format_json(data)
            headers = ""
            if self._headers:
                headers = "Headers:\n%s\n" % self._format_json(
                    self._redacted_headers(self._headers)
                )
            self._add_error(
                "Bad response %s\nURL: %s\nMETHOD: %s\n%s%s%s%s\n%s\n%s"
                % (
                    "-" * 50,
                    response.request.url,
                    response.request.method,
                    params_str,
                    data_str,
                    headers,
                    self._response_to_str(response),
                    e,
                    "-" * 50,
                ),
                log,
            )
            self._bad_response = True
        return response

    @staticmethod
    def _url_origin(url):
        """
        Get the (scheme, hostname, port) of a URL, with the default port
        filled in. Returns None if the URL can't be parsed.
        """
        try:
            parsed = urlparse(url)
            scheme = parsed.scheme.lower()
            port = parsed.port or {"http": 80, "https": 443}.get(scheme)
            return scheme, parsed.hostname, port
        except (AttributeError, TypeError, ValueError):
            return None

    @staticmethod
    def _path_segment(value):
        """
        Percent-encode a value so that it is a single segment of a URL path.
        Values like label names come from webhook payloads, and a "/" in them
        could otherwise change which endpoint is requested.
        Input:
            value: The value to encode, converted with str()
        Return:
            str: The encoded value
        """
        return quote(str(value), safe="")

    @staticmethod
    def _has_dot_segment(url):
        """
        Checks whether the path of a URL has a "." or ".." segment, which
        requests collapses before sending, so the request would go to a
        different path than the URL appears to have.
        Input:
            url[str]: The URL to check
        Return:
            bool: True if the path has a dot segment
        """
        path = urlparse(url).path
        # requests decodes %2E, so check the decoded segments
        return any(unquote(segment) in [".", ".."] for segment in path.split("/"))

    def _allowed_urls(self):
        """
        Get the URLs whose scheme and host requests may be sent to.
        Return:
            list[str]: The allowed URLs
        """
        return [self._api_url]

    def _check_url(self, url, method):
        """
        Checks that a URL is on the same scheme and host as one of the allowed
        URLs (by default, just the configured API URL). Requests are sent with
        the user's credentials, and some URLs come from webhook payloads or API
        responses, so they must never go anywhere else. The path also can't
        have "." or ".." segments that would move the request to another path.
        Input:
            url[str]: URL that is about to be requested
            method[str]: HTTP method, for the error message
        Return:
            bool: True if the URL can be requested
        """
        origin = self._url_origin(url)
        if origin is not None and origin[1]:
            if self._has_dot_segment(url):
                self._add_error(
                    'Refusing to send %s request to %s: "." or ".." in the path'
                    % (method, url)
                )
                self._bad_response = True
                return False
            for allowed_url in self._allowed_urls():
                if origin == self._url_origin(allowed_url):
                    return True
        self._add_error(
            "Refusing to send %s request to %s: not on an API host (%s)"
            % (method, url, ", ".join(str(u) for u in self._allowed_urls()))
        )
        self._bad_response = True
        return False

    def get(self, url, params=None, timeout=None, log=True, raise_forbidden=False):
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
        if not self._check_url(url, "GET"):
            return None
        try:
            timeout = self._timeout(timeout)
            params = self._params(params, True)
            response = self._session.get(
                url,
                params=params,
                timeout=timeout,
                headers=self._headers,
                verify=self._ssl_cert,
            )
        except Exception as e:
            return self._response_exception(url, "GET", e, params=params)

        return self._check_response(
            response, params=params, log=log, raise_forbidden=raise_forbidden
        )

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
        if not self._check_url(url, "POST"):
            return None
        try:
            timeout = self._timeout(timeout)
            params = self._params(params)
            response = self._session.post(
                url,
                params=params,
                json=data,
                timeout=timeout,
                headers=self._headers,
                verify=self._ssl_cert,
            )
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
        if not self._check_url(url, "PATCH"):
            return None
        params = self._params(params)
        try:
            timeout = self._timeout(timeout)
            response = self._session.patch(
                url,
                params=params,
                json=data,
                timeout=timeout,
                headers=self._headers,
                verify=self._ssl_cert,
            )
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
        if not self._check_url(url, "PUT"):
            return None
        params = self._params(params)
        try:
            timeout = self._timeout(timeout)
            response = self._session.put(
                url,
                params=params,
                json=data,
                timeout=timeout,
                headers=self._headers,
                verify=self._ssl_cert,
            )
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
        if not self._check_url(url, "DELETE"):
            return None
        try:
            timeout = self._timeout(timeout)
            response = self._session.delete(
                url,
                params=self._default_params,
                timeout=timeout,
                headers=self._headers,
                verify=self._ssl_cert,
            )
        except Exception as e:
            return self._response_exception(
                url, "DELETE", e, params=self._default_params
            )

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
            while "next" in response.links:
                response = self.get(
                    response.links["next"]["url"],
                    params=params,
                    timeout=timeout,
                    log=log,
                )
                if not self._bad_response and response:
                    all_json.extend(response.json())
                else:
                    break
        except Exception as e:
            self._add_error(
                "Error getting multiple pages at %s\nSent data:\n%s\nError: %s"
                % (url, self._format_json(params), e),
                log,
            )
        return all_json

    @abc.abstractmethod
    def sign_in_url(self):
        """
        Gets the URL to allow the user to sign in.
        Return:
          str: URL
        """

    @abc.abstractmethod
    def can_view_repo(self, owner, name):
        """
        Checks whether or not a user can view a repo
        Input:
          owner[str]: the repo owner
          name[str]: the reo name
        Return:
          bool: Whether or not the repo can be viewed
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
    def update_status(
        self, base, head, state, event_url, description, context, job_stage
    ):
        """
        Update the PR status.
        Input:
          base[models.Commit]: Original commit
          head[models.Commit]: New commit
          state[int]: One of the states defined as class variables above
          event_url[str]: URL back to the moosebuild page
          description[str]: Description of the update
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
    def has_write_access(self, user, repo):
        """
        Check to see if a user has write access to a repo
        Input:
          user[models.GitUser]: User to check against
          repo[models.Repository]: Repository to check against
        Return:
          bool: True if user has write access to repo, False otherwise
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
    def automerge(self, repo, pr_num, head_sha):
        """
        See if a PR can be automerged.
        Input:
          repo[models.Repository]: repository to create/update the issue on
          pr_num[str]: Number of the PR
          head_sha[str]: The tested head SHA of the PR. The PR is only merged
            if its head is still at this SHA.
        """
