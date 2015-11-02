from django.views.decorators.csrf import csrf_exempt
from django.http import HttpResponse, HttpResponseBadRequest, HttpResponseNotAllowed
import logging, traceback
from ci.gitlab.api import GitLabAPI
from ci.gitlab.oauth import GitLabAuth
import json
from ci import event, models

logger = logging.getLogger('ci')

class GitLabException(Exception):
  pass

def process_push(user, auth, data):
  push_event = event.PushEvent()
  push_event.build_user = user

  api = GitLabAPI()
  token = api.get_token(auth)
  url = '{}/{}'.format(api.projects_url(), data['project_id'])
  project = api.get(url, token).json()

  url = '{}/{}'.format(api.users_url(), data['user_id'])

  ref = data['ref'].split('/')[-1] # the format is usually of the form "refs/heads/devel"
  push_event.user = project['namespace']['name']

  push_event.base_commit = event.GitCommitData(
      project['namespace']['name'],
      project['name'],
      ref,
      data['before'],
      data['repository']['url'],
      user.server
      )
  push_event.head_commit = event.GitCommitData(
      project['namespace']['name'],
      project['name'],
      ref,
      data['after'],
      data['repository']['url'],
      user.server
      )
  push_event.comments_url = ''
  push_event.full_text = data
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
  pr_event = event.PullRequestEvent()

  attributes = data['object_attributes']
  action = attributes['state']

  pr_event.pr_number = int(attributes['iid'])

  if action == 'opened' or action == 'synchronize':
    pr_event.action = event.PullRequestEvent.OPENED
  elif action == 'closed' or action == 'merged':
    # The PR is closed which means that the source branch might not exist
    # anymore so we won't be able to fill out the full PullRequestEvent
    # (since we need additional API calls to get all the information we need).
    # So just close this manually.
    close_pr(attributes['target']['namespace'], attributes['target']['name'], pr_event.pr_number, user.server)
    return None
  elif action == 'reopened':
    pr_event.action = event.PullRequestEvent.REOPENED
  else:
    raise GitLabException("Pull request %s contained unknown action." % pr_event.pr_number)

  api = GitLabAPI()
  token = api.get_token(auth)
  target_id = attributes['target_project_id']
  source_id = attributes['source_project_id']
  url = '{}/{}/merge_request/{}'.format(api.projects_url(), target_id, attributes['id'])
  merge_request = get_gitlab_json(api, url, token)
  pr_event.title = merge_request['title']
  if pr_event.title.startswith('[WIP]') or pr_event.title.startswith('WIP:'):
    # We don't want to test when the PR is marked as a work in progress
    logger.info('Ignoring work in progress PR: {}'.format(pr_event.title))
    return None

  url = '{}/{}'.format(api.projects_url(), source_id)
  head = get_gitlab_json(api, url, token)

  url = api.branch_by_id_url(source_id, attributes['source_branch'])
  head_branch = get_gitlab_json(api, url, token)

  url = '{}/{}'.format(api.projects_url(), target_id)
  base = get_gitlab_json(api, url, token)

  url = api.branch_by_id_url(target_id, attributes['target_branch'])
  base_branch = get_gitlab_json(api, url, token)

  pr_event.build_user = user
  pr_event.comments_url = api.comment_api_url(target_id, attributes['id'])
  pr_event.html_url = api.pr_html_url(base['path_with_namespace'], merge_request['iid'])

  pr_event.base_commit = event.GitCommitData(
      attributes['target']['namespace'],
      attributes['target']['name'],
      attributes['target_branch'],
      base_branch['commit']['id'],
      base['ssh_url_to_repo'],
      user.server,
      )

  pr_event.head_commit = event.GitCommitData(
      attributes['source']['namespace'],
      attributes['source']['name'],
      attributes['source_branch'],
      head_branch['commit']['id'],
      head['ssh_url_to_repo'],
      user.server,
      )

  pr_event.full_text = [data, base, base_branch, head, head_branch, merge_request]
  return pr_event

@csrf_exempt
def webhook(request, build_key):
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
    if 'object_kind' in json_data and json_data['object_kind'] == 'merge_request':
      ev = process_pull_request(user, auth, json_data)
      if ev:
        ev.save(request)
      return HttpResponse('OK')
    elif 'commits' in json_data:
      ev = process_push(user, auth, json_data)
      ev.save(request)
      return HttpResponse('OK')
    else:
      err_str = 'Unknown post to gitlab hook : %s' % request.body
      logger.warning(err_str)
      return HttpResponseBadRequest(err_str)
  except Exception as e:
    err_str ="Invalid call to gitlab/webhook for build key %s. Error: %s" % (build_key, traceback.format_exc(e))
    logger.warning(err_str)
    return HttpResponseBadRequest(err_str)

