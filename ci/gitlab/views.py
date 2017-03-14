
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

from django.views.decorators.csrf import csrf_exempt
from django.http import HttpResponse, HttpResponseBadRequest, HttpResponseNotAllowed
import logging, traceback
from ci.gitlab.api import GitLabAPI
from ci.gitlab.oauth import GitLabAuth
import json
from ci import models, PushEvent, PullRequestEvent, GitCommitData
from django.conf import settings

logger = logging.getLogger('ci')

class GitLabException(Exception):
    pass

def process_push(user, auth, data):
    """
    Process the data from a push on a branch.
    Input:
      user: models.GitUser: the build user that created the hook.
      auth: OAuth2Session: session started for the build user
      data: dict: data sent by the webook
    Return:
      models.Event if successful, else None
    """
    push_event = PushEvent.PushEvent()
    push_event.build_user = user

    api = GitLabAPI()
    token = api.get_token(auth)
    url = '{}/{}'.format(api.projects_url(), data['project_id'])
    project = api.get(url, token).json()

    url = '{}/{}'.format(api.users_url(), data['user_id'])

    ref = data['ref'].split('/')[-1] # the format is usually of the form "refs/heads/devel"
    push_event.user = project['namespace']['name']

    push_event.base_commit = GitCommitData.GitCommitData(
        project['namespace']['name'],
        project['name'],
        ref,
        data['before'],
        data['repository']['url'],
        user.server
        )
    push_event.head_commit = GitCommitData.GitCommitData(
        project['namespace']['name'],
        project['name'],
        ref,
        data['after'],
        data['repository']['url'],
        user.server
        )
    push_event.comments_url = ''
    push_event.full_text = [data, project]
    return push_event

def get_gitlab_json(api, url, token):
    data = api.get(url, token).json()
    if 'message' in data.keys():
        raise GitLabException('Error while getting {}: {}'.format(url, data['message']))
    return data

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

def process_pull_request(user, auth, data):
    """
    Process the data from a Pull request.
    Input:
      user: models.GitUser: the build user that created the hook.
      auth: OAuth2Session: session started for the build user
      data: dict: data sent by the webook
    Return:
      models.Event if successful, else None
    """

    pr_event = PullRequestEvent.PullRequestEvent()

    attributes = data['object_attributes']
    action = attributes['state']

    pr_event.pr_number = int(attributes['iid'])

    if action == 'opened' or action == 'synchronize':
        pr_event.action = PullRequestEvent.PullRequestEvent.OPENED
    elif action == 'closed' or action == 'merged':
        # The PR is closed which means that the source branch might not exist
        # anymore so we won't be able to fill out the full PullRequestEvent
        # (since we need additional API calls to get all the information we need).
        # So just close this manually.
        close_pr(attributes['target']['namespace'], attributes['target']['name'], pr_event.pr_number, user.server)
        return None
    elif action == 'reopened':
        pr_event.action = PullRequestEvent.PullRequestEvent.REOPENED
    else:
        raise GitLabException("Pull request %s contained unknown action." % pr_event.pr_number)

    api = GitLabAPI()
    token = api.get_token(auth)
    target_id = attributes['target_project_id']
    target = attributes['target']
    source_id = attributes['source_project_id']
    source = attributes['source']
    pr_event.title = attributes['title']

    for prefix in settings.GITLAB_PR_WIP_PREFIX:
        if pr_event.title.startswith(prefix):
            # We don't want to test when the PR is marked as a work in progress
            logger.info('Ignoring work in progress PR: {}'.format(pr_event.title))
            return None

    pr_event.trigger_user = data['user']['username']
    pr_event.build_user = user
    pr_event.comments_url = api.comment_api_url(target_id, attributes['id'])
    full_path = '{}/{}'.format(target['namespace'], target['name'])
    pr_event.html_url = api.internal_pr_html_url(full_path, attributes['iid'])

    url = api.branch_by_id_url(source_id, attributes['source_branch'])
    try:
        source_branch = get_gitlab_json(api, url, token)
    except Exception as e:
        msg = "CIVET encountered an error retrieving branch `%s/%s:%s`.\n\n" % (source['namespace'], source['name'], attributes['source_branch'])
        msg += "This is typically caused by `%s` not having access to the repository.\n\n" % user.name
        msg += "Please grant `Developer` access to `%s` and try again.\n\n" % user.name
        msg += "Server response:\n\n%s\n" % e
        api.pr_comment(auth, pr_event.comments_url, msg)
        raise

    url = api.branch_by_id_url(target_id, attributes['target_branch'])
    target_branch = get_gitlab_json(api, url, token)

    access_level = api.get_project_access_level(auth, source['namespace'], source['name'])
    if access_level not in ["Developer", "Master", "Owner"]:
        msg = "CIVET does not have proper access to the source repository `%s/%s`.\n\n" % (source['namespace'], source['name'])
        msg += "This can result in CIVET not being able to tell GitLab that CI is in progress.\n\n"
        msg += "`%s` currently has `%s` access.\n\n" % (user.name, access_level)
        msg += "Please grant `Developer` access to `%s` and try again.\n\n" % user.name
        logger.warning(msg)
        api.pr_comment(auth, pr_event.comments_url, msg)

    pr_event.base_commit = GitCommitData.GitCommitData(
        target['namespace'],
        target['name'],
        attributes['target_branch'],
        target_branch['commit']['id'],
        target['ssh_url'],
        user.server,
        )

    pr_event.head_commit = GitCommitData.GitCommitData(
        source['namespace'],
        source['name'],
        attributes['source_branch'],
        source_branch['commit']['id'],
        source['ssh_url'],
        user.server,
        )

    if pr_event.head_commit.exists() and pr_event.action != PullRequestEvent.PullRequestEvent.REOPENED:
        e = "PR {} on {}/{}: got an update but ignoring as it has the same commit {}/{}:{}".format(
                pr_event.pr_number,
                pr_event.base_commit.owner,
                pr_event.base_commit.repo,
                pr_event.head_commit.owner,
                pr_event.head_commit.ref,
                pr_event.head_commit.sha)
        logger.info(e)
        return None
    pr_event.full_text = [data, target_branch, source_branch ]
    pr_event.changed_files = api.get_pr_changed_files(auth, pr_event.base_commit.owner, pr_event.base_commit.repo, pr_event.pr_number)
    return pr_event

@csrf_exempt
def webhook(request, build_key):
    """
    Called by GitLab webhook when an event we are interested in is triggered.
    Input:
      build_key: str: build key that determines the user
    Return:
      HttpResponseNotAllowed for incorrect method
      HttpResponseBadRequest for bad build key or an error occured
      HttpResponse if successful
    """
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])

    user = models.GitUser.objects.filter(build_key=build_key).first()
    if not user:
        err_str = "No user with build key %s" % build_key
        logger.warning(err_str)
        return HttpResponseBadRequest(err_str)

    auth = GitLabAuth().start_session_for_user(user)
    try:
        json_data = json.loads(request.body)
        logger.info('Webhook called: {}'.format(json.dumps(json_data, indent=2)))
        if 'object_kind' in json_data:
            if json_data['object_kind'] == 'merge_request':
                ev = process_pull_request(user, auth, json_data)
                if ev:
                    ev.save(request)
                return HttpResponse('OK')
            elif json_data['object_kind'] == "push" and 'commits' in json_data and json_data["commits"]:
                ev = process_push(user, auth, json_data)
                ev.save(request)
                return HttpResponse('OK')
        err_str = 'Unknown post to gitlab hook : %s' % request.body
        logger.warning(err_str)
        return HttpResponseBadRequest(err_str)
    except Exception as e:
        err_str = "Invalid call to gitlab/webhook for build key %s. Error: %s" % (build_key, traceback.format_exc(e))
        logger.warning(err_str)
        return HttpResponseBadRequest(err_str)
