
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

from ci import models
import re
from django.core.urlresolvers import reverse

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
        oauth_session = job.event.build_user.start_session()
        api = job.event.pull_request.repository.server().api()
        url = job.event.pull_request.review_comments_url
        sha = job.event.head.sha
        msg = "**Caution!** This contains a submodule update"
        # The 2 position will leave the message on the new submodule hash
        api.pr_review_comment(oauth_session, url, sha, mod, 2, msg)
        return True

def check_post_comment(request, job, position):
    """
    Checks to see if we should post a message to the PR.
    """
    output = get_output_by_position(job, position)
    message = find_in_output(output, "CIVET_CLIENT_POST_MESSAGE")
    if not message:
        matches = re.search("^CIVET_CLIENT_START_POST_MESSAGE$\n(.*)\n^CIVET_CLIENT_END_POST_MESSAGE$", output, re.MULTILINE|re.DOTALL)
        if matches:
            message = matches.groups()[0]
    if message and job.event.comments_url:
        oauth_session = job.event.build_user.start_session()
        abs_job_url = request.build_absolute_uri(reverse('ci:view_job', args=[job.pk]))
        msg = "Job [%s](%s) on %s wanted to post the following:\n\n%s" % (job.unique_name(), abs_job_url, job.event.head.sha[:7], message)
        api = job.event.pull_request.repository.server().api()
        url = job.event.comments_url
        api.pr_comment(oauth_session, url, msg)
        return True
    return False

def process_commands(request, job):
    """
    See if we need to check for any commands on this job.
    Commands take the form of an environment variable set on the recipe to
    indicate that we need to check the output for certain key value pairs.
    """
    if job.event.cause != models.Event.PULL_REQUEST:
        return
    for step in job.recipe.steps.prefetch_related("step_environment").all():
        for step_env in step.step_environment.all():
            if step_env.name == "CIVET_SERVER_POST_ON_SUBMODULE_UPDATE" and step_env.value == "1":
                check_submodule_update(job, step.position)
                break
            elif step_env.name == "CIVET_SERVER_POST_COMMENT" and step_env.value == "1":
                check_post_comment(request, job, step.position)
                break
