
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

import TimeUtils
import logging
from ci import models
from django.http import HttpResponseForbidden
from django.conf import settings
logger = logging.getLogger('ci')

def is_collaborator(auth, request_session, build_user, repo, auth_session=None, user=None):
  """
  Checks to see if the signed in user is a collaborator on a repo.
  This will cache the value for a time specified by settings.COLLABORATOR_CACHE_TIMEOUT
  Input:
    auth: an oauth_api.OAuth derived class from one of the git servers
    request_session: A session from HttpRequest.session
    build_user: models.GitUser who has access to check collaborators
    repo: models.Repository to check against
    auth_session: OAuth2Session: optional if there is already a session started
    user: models.GitUser: User to check for. If None then the user will be pulled from the request_session
  Return:
    (bool, models.GitUser) tuple: bool is whether the user is a collaborator
      GitUser is the user from the request_session or None if not signed in
  """
  try:
    if not user:
      user = auth.signed_in_user(repo.user.server, request_session)
    if not user:
      return False, None

    if auth._collaborators_key in request_session:
      collab_dict = request_session[auth._collaborators_key]
      val = collab_dict.get(str(repo))
      timestamp = TimeUtils.get_local_timestamp()
      if val and timestamp < val[1]:
        #logger.info("Using cache for is_collaborator for user %s on %s: %s" % (user, repo, val[0]))
        return val[0], user
    api = repo.user.server.api()
    if auth_session == None:
      auth_session = auth.start_session_for_user(build_user)
    collab_dict = request_session.get(auth._collaborators_key, {})
    val = api.is_collaborator(auth_session, user, repo)
    collab_dict[str(repo)] = (val, TimeUtils.get_local_timestamp() + settings.COLLABORATOR_CACHE_TIMEOUT)
    request_session[auth._collaborators_key] = collab_dict
    logger.info("Is collaborator for user %s on %s: %s" % (user, repo, val))
    return val, user
  except Exception as e:
    logger.warning("Failed to check collbaborater for %s: %s" % (user, e))
    return False, None

def job_permissions(session, job, auth_session=None, user=None):
  """
  Logic for a job to see who can see results, activate,
  cancel, invalidate, or owns the job.
  """
  ret_dict = {'is_owner': False,
      'can_see_results': False,
      'can_admin': False,
      'can_activate': False,
      'can_see_client': False,
        }
  auth = job.event.base.server().auth()
  repo = job.recipe.repository
  if not user:
    user = auth.signed_in_user(repo.user.server, session)
  ret_dict['can_see_results'] = not job.recipe.private
  if user:
    if job.recipe.automatic == models.Recipe.AUTO_FOR_AUTHORIZED:
      if user in job.recipe.auto_authorized.all():
        ret_dict['can_activate'] = True

    collab, user = is_collaborator(auth, session, job.event.build_user, repo, auth_session=auth_session, user=user)
    if collab:
      ret_dict['can_admin'] = True
      ret_dict['can_see_results'] = True
      ret_dict['is_owner'] = user == job.recipe.build_user
      ret_dict['can_activate'] = True
  ret_dict['can_see_client'] = is_allowed_to_see_clients(session)
  return ret_dict

def can_see_results(request, recipe):
  """
  Checks to see if the signed in user can see the results of a recipe
  Input:
    request: HttpRequest
    recipe: models.Recipe to check against
  Return:
    On error, an HttpResponse. Else None.
  """
  build_user = recipe.build_user
  signed_in = build_user.server.auth().signed_in_user(build_user.server, request.session)
  if recipe.private:
    if not signed_in:
      return HttpResponseForbidden('You need to sign in')

    if signed_in != build_user:
      auth = signed_in.server.auth()
      collab, user = is_collaborator(auth, request.session, build_user, recipe.repository, user=signed_in)
      if not collab:
        return HttpResponseForbidden('Not authorized to view these results')
  return None

def is_allowed_to_cancel(session, ev):
  """
  A convience function to check to see if the signed in user is allowed to cancel an event.
  Input:
    session: session from HttpRequest
    ev: models.Event to check against
  Return:
    (bool, models.GitUser) tuple: bool is whether they are allowed. Gituser is the signed in user or None if not signed in.
  """
  auth = ev.base.server().auth()
  allowed, signed_in_user = is_collaborator(auth, session, ev.build_user, ev.base.branch.repository)
  return allowed, signed_in_user


def is_allowed_to_see_clients(session):
  """
  Checks to see if a user is allowed to see the client names.
  Note that the "is_collaborator" check isn't reliable here
  because with GitHub only users who have push access to the
  repository can actually check the collaborator list.
  This is why we usually start a session as a user that does have
  push access.
  So the user of this session might be a collaborator but
  have no way to check to see if he is a collaborator.
  For the core team, who all have push access, this isn't
  a problem and those are really the only ones that need
  to see the clients.
  """
  val = session.get("allowed_to_see_clients")
  if val and TimeUtils.get_local_timestamp() < val[1]:
    #logger.info("Using cached value for allowed_to_see_clients: %s" % val[0])
    return val[0]

  for server in settings.INSTALLED_GITSERVERS:
    gitserver = models.GitServer.objects.get(host_type=server)
    auth = gitserver.auth()
    user = auth.signed_in_user(gitserver, session)
    if not user:
      continue
    for owner in settings.AUTHORIZED_OWNERS:
      repo_obj = models.Repository.objects.filter(user__name=owner, user__server=gitserver).first()
      if not repo_obj:
        continue
      collab, user = is_collaborator(auth, session, user, repo_obj)
      if collab:
        session["allowed_to_see_clients"] = (collab, TimeUtils.get_local_timestamp() + settings.COLLABORATOR_CACHE_TIMEOUT)
        logger.info("%s is allowed to see clients" % user)
        return True
    logger.info("%s is NOT allowed to see clients on %s" % (user, gitserver))
  session["allowed_to_see_clients"] = (False, TimeUtils.get_local_timestamp() + settings.COLLABORATOR_CACHE_TIMEOUT)
  logger.info("%s is NOT allowed to see clients" % user)
  return False
