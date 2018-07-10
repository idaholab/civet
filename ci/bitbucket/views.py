
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
from django.views.decorators.csrf import csrf_exempt
from django.http import HttpResponse, HttpResponseBadRequest, HttpResponseNotAllowed
import logging, traceback
from ci import models, PushEvent, PullRequestEvent, GitCommitData
import json

logger = logging.getLogger('ci')

class BitBucketException(Exception):
    pass

def process_push(user, data):
    push_event = PushEvent.PushEvent()
    push_event.build_user = user

    push_data = data['push']
    push_event.user = data['actor']['username']
    repo_data = data['repository']
    new_data = push_data['changes'][-1].get('new')
    old_data = push_data['changes'][-1].get('old')
    if not old_data:
        raise BitBucketException("Push event doesn't have old data!")
    if not new_data:
        raise BitBucketException("Push event doesn't have new data!")
    ref = new_data['name']
    owner = repo_data['owner']['username']
    ssh_url = 'git@bitbucket.org:{}/{}.git'.format(owner, repo_data['name'])
    push_event.base_commit = GitCommitData.GitCommitData(
        owner,
        repo_data['name'],
        ref,
        old_data['target']['hash'],
        ssh_url,
        user.server
        )
    push_event.head_commit = GitCommitData.GitCommitData(
        owner,
        repo_data['name'],
        ref,
        new_data['target']['hash'],
        ssh_url,
        user.server
        )
    if 'message' in new_data['target']:
        push_event.description = new_data['target']['message'].split('\n')[0][:200]
    url = user.api()._commit_comment_url(repo_data['name'], owner, new_data['target']['hash'])
    push_event.comments_url = url
    push_event.full_text = data
    return push_event

def process_pull_request(user, data):
    pr_event = PullRequestEvent.PullRequestEvent()
    pr_data = data['pullrequest']

    action = pr_data['state']

    pr_event.pr_number = int(pr_data['id'])

    if action == 'OPEN':
        pr_event.action = PullRequestEvent.PullRequestEvent.OPENED
    elif action == 'MERGED' or action == 'DECLINED':
        pr_event.action = PullRequestEvent.PullRequestEvent.CLOSED
    else:
        raise BitBucketException("Pull request #%s contained unknown action." % pr_event.pr_number)

    api = user.api()
    pr_event.build_user = user
    html_url = pr_data['links']['html']['href']
    pr_event.title = pr_data['title']
    pr_event.html_url = html_url
    pr_event.trigger_user = pr_data['author']['username']

    base_data = pr_data['destination']
    repo_data = base_data['repository']
    owner = repo_data['full_name'].split('/')[0]
    ssh_url = 'git@bitbucket.org:{}/{}.git'.format(owner, repo_data['name'])
    pr_event.comments_url = api._pr_comment_api_url(owner, repo_data['name'], pr_event.pr_number)

    pr_event.base_commit = GitCommitData.GitCommitData(
        owner,
        repo_data['name'],
        base_data['branch']['name'],
        base_data['commit']['hash'],
        ssh_url,
        user.server
        )
    head_data = pr_data['source']
    repo_data = head_data['repository']
    owner = repo_data['full_name'].split('/')[0]
    ssh_url = 'git@bitbucket.org:{}/{}.git'.format(owner, repo_data['name'])
    pr_event.head_commit = GitCommitData.GitCommitData(
        owner,
        repo_data['name'],
        head_data['branch']['name'],
        head_data['commit']['hash'],
        ssh_url,
        user.server
        )

    pr_event.full_text = data
    return pr_event

@csrf_exempt
def webhook(request, build_key):
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])

    try:
        data = json.loads(request.body)
    except ValueError:
        err_str = "Bad json in github webhook request"
        logger.warning(err_str)
        return HttpResponseBadRequest(err_str)

    user = models.GitUser.objects.filter(build_key=build_key).first()
    if not user:
        logger.warning("No user with build key %s" % build_key)
        return HttpResponseBadRequest("Error")

    if user.recipes.count() == 0:
        logger.warning("User '%s' does not have any recipes" % user)
        return HttpResponseBadRequest("Error")

    return process_event(request, user, data)

def process_event(request, user, json_data):
    try:
        logger.info('Webhook called:\n{}'.format(json.dumps(json_data, indent=2)))
        if 'pullrequest' in json_data:
            ev = process_pull_request(user, json_data)
            if ev:
                ev.save(request)
            return HttpResponse('OK')
        elif 'push' in json_data:
            ev = process_push(user, json_data)
            ev.save(request)
            return HttpResponse('OK')
        else:
            err_str = 'Unknown post to bitbucket hook'
            logger.warning(err_str)
            return HttpResponseBadRequest(err_str)
    except Exception:
        err_str ="Invalid call to bitbucket/webhook for user %s. Error: %s" % (user, traceback.format_exc())
        logger.warning(err_str)
        return HttpResponseBadRequest(err_str)
