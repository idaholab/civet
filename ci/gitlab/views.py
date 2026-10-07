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
from django.conf import settings
from django.views.decorators.csrf import csrf_exempt
from django.http import HttpResponse, HttpResponseBadRequest
import logging
from ci import models, PushEvent, PullRequestEvent, GitCommitData, tasks
from ci.webhook import handle_webhook
import hmac

logger = logging.getLogger("ci")


class GitLabException(Exception):
    pass


def is_valid_token(request, body, secret):
    """
    Checks the X-Gitlab-Token header value of a webhook request.
    Input:
      request[HttpRequest]: the webhook request
      body[bytes]: the raw request body, which isn't used
      secret[str]: the webhook's secret
    Return:
      bool: True if the token is the secret
    """
    token = request.headers.get("X-Gitlab-Token", "")
    if not token:
        return False
    return hmac.compare_digest(token.encode("utf-8", "replace"), secret.encode("utf-8"))


def process_push(hook, data):
    """
    Process the data from a push on a branch.
    Input:
      hook: models.RepositoryWebhook: the webhook that was called
      data: dict: data sent by the webook
    Return:
      models.Event if successful, else None
    """
    user = hook.build_user
    git_api = user.api()
    push_event = PushEvent.PushEvent()
    push_event.build_user = user
    url = git_api._project_url(data["project_id"])
    project = git_api.get(url).json()
    hook.check_repository(project["namespace"]["name"], project["name"])

    ref = data["ref"].split("/")[
        -1
    ]  # the format is usually of the form "refs/heads/devel"
    push_event.user = project["namespace"]["name"]

    push_event.base_commit = GitCommitData.GitCommitData(
        project["namespace"]["name"],
        project["name"],
        ref,
        data["before"],
        data["repository"]["url"],
        user.server,
    )
    push_event.head_commit = GitCommitData.GitCommitData(
        project["namespace"]["name"],
        project["name"],
        ref,
        data["after"],
        data["repository"]["url"],
        user.server,
    )
    push_event.comments_url = ""
    push_event.full_text = [data, project]
    push_event.save()


def close_pr(owner, repo, pr_num, server):
    user, created = models.GitUser.objects.get_or_create(name=owner, server=server)
    if created:
        # if the user was created then we won't have this PR in the DB
        return

    repo, created = models.Repository.objects.get_or_create(user=user, name=repo)
    if created:
        # if the repo was created then we won't have this PR in the DB
        return

    try:
        pr = models.PullRequest.objects.get(number=pr_num, repository=repo)
        pr.closed = True
        pr.save()
        logger.info("Closed pull request %s on %s" % (pr_num, repo))
    except models.PullRequest.DoesNotExist:
        pass


def process_pull_request(hook, data):
    """
    Process the data from a Pull request.
    Input:
      hook: models.RepositoryWebhook: the webhook that was called
      data: dict: data sent by the webook
    Return:
      models.Event if successful, else None
    """

    user = hook.build_user
    git_api = user.api()
    pr_event = PullRequestEvent.PullRequestEvent()

    attributes = data["object_attributes"]
    hook.check_repository(
        attributes["target"]["path_with_namespace"].split("/")[0],
        attributes["target"]["name"],
    )
    action = attributes["state"]

    pr_event.pr_number = int(attributes["iid"])

    if action == "opened" or action == "synchronize":
        pr_event.action = PullRequestEvent.PullRequestEvent.OPENED
    elif action == "closed" or action == "merged":
        # The PR is closed which means that the source branch might not exist
        # anymore so we won't be able to fill out the full PullRequestEvent
        # (since we need additional API calls to get all the information we need).
        # So just close this manually.
        close_pr(
            attributes["target"]["path_with_namespace"].split("/")[0],
            attributes["target"]["name"],
            pr_event.pr_number,
            user.server,
        )
        return None
    elif action == "reopened":
        pr_event.action = PullRequestEvent.PullRequestEvent.REOPENED
    else:
        raise GitLabException(
            "Pull request %s contained unknown action." % pr_event.pr_number
        )

    target = attributes["target"]
    source_id = int(attributes["source_project_id"])
    source = attributes["source"]
    pr_event.title = attributes["title"]

    server_config = user.server.server_config()
    for prefix in server_config.get("pr_wip_prefix", []):
        if pr_event.title.startswith(prefix):
            # We don't want to test when the PR is marked as a work in progress
            logger.info("Ignoring work in progress PR: {}".format(pr_event.title))
            return None

    pr_event.trigger_user = data["user"]["username"]
    pr_event.build_user = user
    # The target is the webhook's repository, so use its path rather than
    # the IDs or paths in the payload, which could point at another project
    full_path = "{}/{}".format(hook.repository.user.name, hook.repository.name)
    pr_event.comments_url = git_api._comment_api_url(full_path, pr_event.pr_number)
    pr_event.html_url = git_api._pr_html_url(full_path, pr_event.pr_number)

    url = git_api._branch_by_id_url(source_id, attributes["source_branch"])
    response = git_api.get(url)
    if not response or git_api._bad_response:
        msg = "CIVET encountered an error retrieving branch `%s:%s`.\n\n" % (
            source["path_with_namespace"],
            attributes["source_branch"],
        )
        msg += (
            "This is typically caused by `%s` not having access to the repository.\n\n"
            % user.name
        )
        msg += "Please grant `Developer` access to `%s` and try again.\n\n" % user.name
        tasks.pr_comment.enqueue(user.pk, pr_event.comments_url, msg)
        raise GitLabException(msg)
    else:
        source_branch = response.json()

    url = git_api._branch_url(full_path, attributes["target_branch"])
    target_branch = git_api.get(url).json()

    access_level = git_api._get_project_access_level(source["path_with_namespace"])
    if access_level not in ["Developer", "Master", "Owner"]:
        msg = "CIVET does not have proper access to the source repository `%s`.\n\n" % (
            source["path_with_namespace"]
        )
        msg += "This can result in CIVET not being able to tell GitLab that CI is in progress.\n\n"
        msg += "`%s` currently has `%s` access.\n\n" % (user.name, access_level)
        msg += "Please grant `Developer` access to `%s` and try again.\n\n" % user.name
        logger.warning(msg)
        tasks.pr_comment.enqueue(user.pk, pr_event.comments_url, msg)

    pr_event.base_commit = GitCommitData.GitCommitData(
        target["path_with_namespace"].split("/")[0],
        target["name"],
        attributes["target_branch"],
        target_branch["commit"]["id"],
        target["ssh_url"],
        user.server,
    )

    pr_event.head_commit = GitCommitData.GitCommitData(
        source["path_with_namespace"].split("/")[0],
        source["name"],
        attributes["source_branch"],
        source_branch["commit"]["id"],
        source["ssh_url"],
        user.server,
    )

    if (
        pr_event.head_commit.exists()
        and pr_event.action != PullRequestEvent.PullRequestEvent.REOPENED
    ):
        e = "PR {} on {}/{}: got an update but ignoring as it has the same commit {}/{}:{}".format(
            pr_event.pr_number,
            pr_event.base_commit.owner,
            pr_event.base_commit.repo,
            pr_event.head_commit.owner,
            pr_event.head_commit.ref,
            pr_event.head_commit.sha,
        )
        logger.info(e)
        return None
    pr_event.full_text = [data, target_branch, source_branch]
    pr_event.changed_files = git_api._get_pr_changed_files(
        pr_event.base_commit.owner, pr_event.base_commit.repo, pr_event.pr_number
    )
    # The webhook user is whoever triggered the event, not necessarily the author
    pr_event.author = git_api._get_username(attributes["author_id"])
    pr_event.save()


@csrf_exempt
def webhook(request, hook_id):
    """
    Called by GitLab webhook when an event we are interested in is triggered.
    See ci.webhook.handle_webhook.
    """
    return handle_webhook(
        request, hook_id, settings.GITSERVER_GITLAB, is_valid_token, process_event
    )


def process_event(hook, json_data):
    object_kind = json_data.get("object_kind")
    if object_kind == "merge_request":
        process_pull_request(hook, json_data)
    elif object_kind == "push":
        if json_data.get("commits"):
            process_push(hook, json_data)
    else:
        err_str = "Unknown post to gitlab hook"
        logger.warning(err_str)
        return HttpResponseBadRequest(err_str)
    return HttpResponse("OK")
