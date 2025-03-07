
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
from ci import models
import re

def find_in_output(output, key):
    """
    Find a key in the output and return its value.
    """
    matches = re.search("^%s=(.*)" % key, output, re.MULTILINE)
    if matches:
        return matches.groups()[0]
    return None

def get_output_by_position(job, position):
    """
    Utility function to get the output of a job step result by position
    """
    return job.step_results.get(position=position).output

def get_name_by_position(job, position):
    """
    Utility function to get the output of a job step name by position
    """
    return job.step_results.get(position=position).name

def check_submodule_update(job, position):
    """
    Checks to see if certain submodules have been updated and post a comment to the PR if so.
    """
    output = get_output_by_position(job, position)
    modules = find_in_output(output, "CIVET_CLIENT_SUBMODULE_UPDATES")
    if not modules:
        return False
    if not job.event.pull_request or not job.event.pull_request.review_comments_url:
        return False
    for mod in modules.split():
        api = job.event.build_user.api()
        url = job.event.pull_request.review_comments_url
        sha = job.event.head.sha
        msg = "**Caution!** This contains a submodule update"
        # The 2 position will leave the message on the new submodule hash
        api.pr_review_comment(url, sha, mod, 2, msg)
        return True

def ensure_single_new_comment(api, builduser, url, msg, comment_re):
    """
    Adds a new comment and deletes any existing similar comments.
    The difference between this and edit_comment() is that this method will
    typically cause a new email to be sent.
    """
    comments = api.get_pr_comments(url, builduser.name, comment_re)
    for c in comments:
        api.remove_pr_comment(c)
    api.pr_comment(url, msg)

def edit_comment(api, builduser, url, msg, comment_re):
    """
    Replaces an existing comment with a new one. Removes any similar
    messages except the first one.
    """
    comments = api.get_pr_comments(url, builduser.name, comment_re)
    if comments:
        for c in comments[1:]:
            api.remove_pr_comment(c)
        api.edit_pr_comment(comments[0], msg)
    else:
        api.pr_comment(url, msg)

def check_post_comment(job, position, edit, delete):
    """
    Checks to see if we should post a message to the PR.
    """
    output = get_output_by_position(job, position)
    step_name = get_name_by_position(job, position)
    message = find_in_output(output, "CIVET_CLIENT_POST_MESSAGE")
    if not message:
        matches = re.search("^CIVET_CLIENT_START_POST_MESSAGE$\n(.*)\n^CIVET_CLIENT_END_POST_MESSAGE$",
                output, re.MULTILINE|re.DOTALL)
        if matches:
            message = matches.groups()[0]
    if message and job.event.comments_url:
        builduser = job.event.build_user
        msg = f'Job [{job.unique_name()}]({job.absolute_url()}), step {step_name} on ' \
              f'{job.event.head.short_sha()} wanted to post the following:\n\n' \
              f'{message}'
        api = builduser.api()
        url = job.event.comments_url
        comment_re = r"^Job \[%s\]\(.*\), step %s on \w+ wanted to post the following:" % (job.unique_name(),
                                                                                           step_name)

        if edit:
            msg = "%s\n\nThis comment will be updated on new commits." % msg
            edit_comment(api, builduser, url, msg, comment_re)
        elif delete:
            ensure_single_new_comment(api, builduser, url, msg, comment_re)
        else:
            api.pr_comment(url, msg)
        return True
    return False

def process_commands(job):
    """
    See if we need to check for any commands on this job.
    Commands take the form of an environment variable set on the recipe to
    indicate that we need to check the output for certain key value pairs.
    """
    if job.event.cause != models.Event.PULL_REQUEST:
        return
    for step in job.recipe.steps.prefetch_related("step_environment").all():
        edit = False
        delete = False
        for step_env in step.step_environment.all():
            if step_env.name == "CIVET_SERVER_POST_REMOVE_OLD" and step_env.value == "1":
                delete = True
                break
            elif step_env.name == "CIVET_SERVER_POST_EDIT_EXISTING" and step_env.value == "1":
                edit = True
                break
        for step_env in step.step_environment.all():
            if step_env.name == "CIVET_SERVER_POST_ON_SUBMODULE_UPDATE" and step_env.value == "1":
                check_submodule_update(job, step.position)
                break
            elif step_env.name == "CIVET_SERVER_POST_COMMENT" and step_env.value == "1":
                check_post_comment(job, step.position, edit, delete)
                break
