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
from django.http import HttpResponse, HttpResponseBadRequest, HttpResponseNotAllowed
import logging, traceback
from ci.github.api import GitException
from ci import models, PushEvent, PullRequestEvent, GitCommitData, ReleaseEvent
import hashlib
import hmac
import json

logger = logging.getLogger("ci")


def signed_server_names(body, signature):
    """
    Gets the hostnames of the installed GitHub servers whose "webhook_secret"
    produces the X-Hub-Signature-256 header value for the request body.
    This only depends on the request, never on the build key, so it is the
    same work for every build key.
    Input:
      body[bytes]: the raw request body
      signature[str]: value of the X-Hub-Signature-256 header
    Return:
      list[str]: hostnames of the servers that signed the body
    """
    names = []
    if not signature:
        return names
    signature = signature.encode("utf-8", "replace")
    for server in settings.INSTALLED_GITSERVERS:
        secret = server.get("webhook_secret")
        if server.get("type") != settings.GITSERVER_GITHUB or not secret:
            continue
        digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
        if hmac.compare_digest(("sha256=%s" % digest).encode("utf-8"), signature):
            names.append(server.get("hostname", ""))
    return names


def process_push(user, data):
    push_event = PushEvent.PushEvent()
    push_event.build_user = user
    push_event.user = data["sender"]["login"]

    repo_data = data["repository"]
    ref = data["ref"].split("/")[
        -1
    ]  # the format is usually of the form "refs/heads/devel"
    head_commit = data.get("head_commit")
    if head_commit:
        push_event.description = head_commit["message"].split("\n\n")[0][:200]
        push_event.changed_files = (
            head_commit["modified"] + head_commit["removed"] + head_commit["added"]
        )
        if (
            push_event.description.startswith("Merge commit '")
            and len(push_event.description) > 21
        ):
            push_event.description = "Merge commit %s" % push_event.description[14:20]

    push_event.base_commit = GitCommitData.GitCommitData(
        repo_data["owner"]["name"],
        repo_data["name"],
        ref,
        data["before"],
        repo_data["ssh_url"],
        user.server,
    )
    push_event.head_commit = GitCommitData.GitCommitData(
        repo_data["owner"]["name"],
        repo_data["name"],
        ref,
        data["after"],
        repo_data["ssh_url"],
        user.server,
    )
    api = user.api()
    url = api._commit_comment_url(
        repo_data["name"], repo_data["owner"]["name"], data["after"]
    )
    push_event.comments_url = url
    push_event.full_text = data
    push_event.save()


def process_pull_request(user, data):
    pr_event = PullRequestEvent.PullRequestEvent()
    pr_data = data["pull_request"]

    action = data["action"]

    pr_event.pr_number = int(data["number"])

    state = pr_data["state"]
    if (
        action == "opened"
        or action == "synchronize"
        or (action == "edited" and state == "open")
    ):
        pr_event.action = PullRequestEvent.PullRequestEvent.OPENED
    elif action == "closed":
        pr_event.action = PullRequestEvent.PullRequestEvent.CLOSED
    elif action == "reopened":
        pr_event.action = PullRequestEvent.PullRequestEvent.REOPENED
    elif action in [
        "labeled",
        "unlabeled",
        "assigned",
        "unassigned",
        "review_requested",
        "review_request_removed",
        "edited",
        "auto_merge_enabled",
        "ready_for_review",
        "converted_to_draft",
        "auto_merge_disabled",
        "locked",
    ]:
        # actions that we don't support. "edited" is not supported if the PR is closed.
        logger.info(
            'Ignoring github action "{}" on PR: #{}: {}'.format(
                action, data["number"], pr_data["title"]
            )
        )
        return None
    else:
        raise GitException(
            "Pull request %s contained unknown action: %s"
            % (pr_event.pr_number, action)
        )

    pr_event.trigger_user = pr_data["user"]["login"]
    pr_event.author = pr_data["user"]["login"]
    pr_event.build_user = user
    pr_event.title = pr_data["title"]

    server_config = user.server.server_config()
    for prefix in server_config.get("pr_wip_prefix", []):
        if pr_event.title.startswith(prefix):
            # We don't want to test when the PR is marked as a work in progress
            logger.info("Ignoring work in progress PR: {}".format(pr_event.title))
            return None

    pr_event.html_url = pr_data["html_url"]

    base_data = pr_data["base"]
    pr_event.base_commit = GitCommitData.GitCommitData(
        base_data["repo"]["owner"]["login"],
        base_data["repo"]["name"],
        base_data["ref"],
        base_data["sha"],
        base_data["repo"]["ssh_url"],
        user.server,
    )
    head_data = pr_data["head"]
    pr_event.head_commit = GitCommitData.GitCommitData(
        head_data["repo"]["owner"]["login"],
        head_data["repo"]["name"],
        head_data["ref"],
        head_data["sha"],
        head_data["repo"]["ssh_url"],
        user.server,
    )

    labels = pr_data.get("labels")
    if labels is not None:
        pr_event.labels = [label["name"] for label in labels]

    gapi = user.api()
    # Build the comment URLs from the configured API URL instead of taking them
    # from the payload; they are requested with the build user's token
    pr_event.comments_url = gapi._pr_comment_url(
        pr_event.base_commit.owner, pr_event.base_commit.repo, pr_event.pr_number
    )
    pr_event.review_comments_url = gapi._pr_review_comment_url(
        pr_event.base_commit.owner, pr_event.base_commit.repo, pr_event.pr_number
    )
    if action == "synchronize":
        # synchronize is used when updating due to a new push in the branch that the PR is tracking
        gapi._remove_pr_todo_labels(
            pr_event.base_commit.owner,
            pr_event.base_commit.repo,
            pr_event.pr_number,
            labels=pr_event.labels,
        )

    pr_event.full_text = data
    # Changed files aren't used when closing. If there is already an event for this
    # base and head (ie the PR was edited or reopened), then its changed files are
    # the same, so we can skip asking the server again.
    if pr_event.action != PullRequestEvent.PullRequestEvent.CLOSED:
        existing_event = pr_event.existing_event()
        if existing_event is not None:
            pr_event.changed_files = existing_event.get_changed_files()
        else:
            pr_event.changed_files = gapi._get_pr_changed_files(
                pr_event.base_commit.owner,
                pr_event.base_commit.repo,
                pr_event.pr_number,
            )
    pr_event.save()


def process_release(user, data):
    """
    Called on the "release" webhook when a user does a GitHub release.
    A GitHub release is basically just a tag along with some other niceties like
    auto tarballing the source code for the tag.
    """
    rel_event = ReleaseEvent.ReleaseEvent()
    rel_event.build_user = user
    release = data["release"]

    rel_event.release_tag = release["tag_name"]
    repo_data = data["repository"]
    rel_event.description = "Release: %s" % release["name"][:150]
    branch = release["target_commitish"]
    repo_name = repo_data["name"]
    owner = repo_data["owner"]["login"]

    if len(branch) == 40:
        # We have an actual SHA but the branch information is not anywhere so we just assume the commit was on master
        tag_sha = branch
        branch = "master"
    else:
        # Doesn't look like a SHA so assume it is a branch and grab the SHA from the release tag
        api = user.api()
        tag_sha = api._tag_sha(owner, repo_name, rel_event.release_tag)
        if tag_sha is None:
            raise GitException(
                "Couldn't find SHA for %s/%s:%s."
                % (owner, repo_name, rel_event.release_tag)
            )

    logger.info(
        "Release '%s' on %s/%s:%s using commit %s"
        % (rel_event.release_tag, owner, repo_name, branch, tag_sha)
    )

    rel_event.commit = GitCommitData.GitCommitData(
        owner, repo_name, branch, tag_sha, repo_data["ssh_url"], user.server
    )
    rel_event.full_text = data
    rel_event.save()


@csrf_exempt
def webhook(request, build_key):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    # Read the body and check its signature before anything depends on the
    # build key, so an unsigned request gets the same answer for every key.
    server_names = signed_server_names(
        request.body, request.headers.get("X-Hub-Signature-256", "")
    )
    if not server_names:
        logger.warning("Bad signature on github webhook for build key %s" % build_key)
        return HttpResponseBadRequest("Error")

    try:
        data = json.loads(request.body)
    except ValueError:
        err_str = "Bad json in github webhook request"
        logger.warning(err_str)
        return HttpResponseBadRequest(err_str)

    user = models.GitUser.objects.filter(
        build_key=build_key,
        server__host_type=settings.GITSERVER_GITHUB,
        server__name__in=server_names,
    ).first()
    if not user:
        repo = data.get("repository", {}).get("html_url")
        logger.warning("No user with build key %s for repo %s" % (build_key, repo))
        return HttpResponseBadRequest("Error")

    if user.recipes.count() == 0:
        logger.warning("User '%s' does not have any recipes" % user)
        return HttpResponseBadRequest("Error")

    return process_event(user, data)


def process_event(user, json_data):
    ret = HttpResponse("OK")
    try:
        logger.info("Webhook called:\n{}".format(json.dumps(json_data, indent=2)))

        if "pull_request" in json_data:
            process_pull_request(user, json_data)
        elif "commits" in json_data:
            process_push(user, json_data)
        elif "release" in json_data:
            process_release(user, json_data)
        elif "zen" in json_data:
            # this is a ping that gets called when first
            # installing a hook. Just log it and move on.
            logger.info("Got ping for user {}".format(user.name))
        else:
            err_str = "Unknown post to github hook"
            logger.warning(err_str)
            ret = HttpResponseBadRequest(err_str)
    except Exception:
        err_str = "Invalid call to github/webhook for user %s. Error: %s" % (
            user,
            traceback.format_exc(),
        )
        logger.warning(err_str)
        # The traceback can contain request data, so it only goes to the log
        ret = HttpResponseBadRequest("Error", content_type="text/plain")
    return ret
