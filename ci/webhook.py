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
from django.http import HttpResponseBadRequest, HttpResponseNotAllowed
from ci import models
import json
import logging
import traceback

logger = logging.getLogger("ci")


def branch_from_ref(ref):
    """
    Gets the branch name from the ref of a push webhook, which is shared by the
    webhook views of all the git servers.
    The ref is of the form "refs/heads/devel" and the branch name can contain
    slashes, so all of it after the prefix is kept.
    Input:
      ref[str]: the ref that was pushed to
    Return:
      str: the name of the branch, or None if the ref is not a branch (e.g. a tag)
    """
    prefix = "refs/heads/"
    if ref.startswith(prefix) and len(ref) > len(prefix):
        return ref[len(prefix) :]
    logger.info("Ignoring push to non-branch ref %s" % ref)
    return None


def handle_webhook(request, hook_id, host_type, is_authentic, process_event):
    """
    Handles a webhook request from a git server, which is shared by the
    webhook views of all the git servers.
    Input:
      request[HttpRequest]: the request from the git server
      hook_id[str]: hook_id of the models.RepositoryWebhook
      host_type[int]: settings.GITSERVER_* type of the git server
      is_authentic[func]: called with the request, the raw body and the
        webhook's secret; returns whether the request came from the git server
      process_event[func]: called with the webhook and the json data;
        returns the HttpResponse
    Return:
      HttpResponseNotAllowed for incorrect method
      HttpResponseBadRequest for a bad webhook or authentication, or an error occured
      HttpResponse if successful
    """
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    # Read the body first so that an oversized body gets the same answer
    # whether or not the webhook exists
    body = request.body

    name = dict(models.GitServer.SERVER_TYPE)[host_type].lower()
    hook = (
        models.RepositoryWebhook.objects.select_related(
            "build_user__server", "repository__user"
        )
        .filter(hook_id=hook_id, repository__user__server__host_type=host_type)
        .first()
    )
    if not hook:
        logger.warning("No %s webhook with id %s" % (name, hook_id))
        return HttpResponseBadRequest("Error")

    if not is_authentic(request, body, hook.secret):
        logger.warning("Failed authentication on %s webhook for %s" % (name, hook))
        return HttpResponseBadRequest("Error")

    try:
        data = json.loads(body)
    except ValueError:
        err_str = "Bad json in %s webhook request" % name
        logger.warning(err_str)
        return HttpResponseBadRequest(err_str)

    if hook.build_user.recipes.count() == 0:
        logger.warning("User '%s' does not have any recipes" % hook.build_user)
        return HttpResponseBadRequest("Error")

    # Without a token every request to the git server as the build user
    # fails, so don't create the event and run jobs that can't report back.
    # The request is authenticated by now, so the git server's webhook
    # deliveries can show why.
    if not hook.build_user.token:
        err_str = "Build user '%s' has no token; sign in to CIVET as '%s'" % (
            hook.build_user,
            hook.build_user,
        )
        logger.warning(err_str)
        return HttpResponseBadRequest(err_str, content_type="text/plain")

    try:
        logger.info("Webhook called:\n{}".format(json.dumps(data, indent=2)))
        return process_event(hook, data)
    except Exception:
        err_str = "Invalid call to %s/webhook for %s. Error: %s" % (
            name,
            hook,
            traceback.format_exc(),
        )
        logger.warning(err_str)
        # The traceback can contain request data, so it only goes to the log
        return HttpResponseBadRequest("Error", content_type="text/plain")
