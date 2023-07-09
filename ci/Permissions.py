
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
import logging
from ci import models, TimeUtils
from django.conf import settings
logger = logging.getLogger('ci')

def is_collaborator(request_session, build_user, repo, user=None):
    """
    Checks to see if the signed in user is a collaborator on a repo.
    This will cache the value for a time specified by settings.PERMISSION_CACHE_TIMEOUT
    Input:
      request_session: A session from HttpRequest.session
      build_user: models.GitUser who has access to check collaborators
      repo: models.Repository to check against
      user: models.GitUser: User to check for. If None then the user will be pulled from the request_session
    Return:
      (bool, models.GitUser) tuple: bool is whether the user is a collaborator
        GitUser is the user from the request_session or None if not signed in
    """
    server = repo.server()
    if not user:
        user = server.signed_in_user(request_session)
    if not user:
        return False

    auth = server.auth()
    if auth._collaborators_key in request_session:
        collab_dict = request_session[auth._collaborators_key]
        val = collab_dict.get(str(repo))
        timestamp = TimeUtils.get_local_timestamp()
        # Check to see if their permissions are still valid
        if val and timestamp < val[1]:
            return val[0]

    api = build_user.api()

    collab_dict = request_session.get(auth._collaborators_key, {})
    val = api.is_collaborator(user, repo)
    collab_dict[str(repo)] = (val, TimeUtils.get_local_timestamp() + settings.PERMISSION_CACHE_TIMEOUT)
    request_session[auth._collaborators_key] = collab_dict
    logger.info("Is collaborator for user '%s' on %s: %s" % (user, repo, val))
    return val

def job_permissions(session, job):
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
    server = job.event.base.server()
    repo = job.recipe.repository
    user = server.signed_in_user(session)

    ret_dict['can_see_client'] = is_allowed_to_see_clients(session)

    if user == job.recipe.build_user:
        # The owner should be able to do everything
        ret_dict['is_owner'] = True
        ret_dict['can_admin'] = True
        ret_dict['can_see_results'] = True
        ret_dict['can_activate'] = True
        return ret_dict

    ret_dict['can_see_results'] = can_see_results(session, job.recipe)

    if not user:
        return ret_dict

    if job.recipe.automatic == models.Recipe.AUTO_FOR_AUTHORIZED:
        if user in job.recipe.auto_authorized.all():
            ret_dict['can_activate'] = True

    if job.recipe.private and ret_dict['can_see_results']:
        ret_dict['can_admin'] = True
        ret_dict['can_activate'] = True
    elif not job.recipe.private:
        collab = is_collaborator(session, job.event.build_user, repo, user=user)
        if collab:
            ret_dict['can_admin'] = True
            ret_dict['can_activate'] = True
    return ret_dict

def can_see_results(session, recipe):
    """
    Checks to see if the signed in user can see the results of a recipe
    Input:
      request: HttpRequest
      recipe: models.Recipe to check against
    Return:
      On error, an HttpResponse. Else None.
    """
    if not recipe.private:
        return True

    build_user = recipe.build_user
    signed_in = build_user.server.auth().signed_in_user(build_user.server, session)

    if signed_in == build_user:
        return True

    if not signed_in:
        return False

    api = signed_in.api()

    # if viewable_by_teams was specified we check if
    # the signed in user is a member of one of the teams
    for team in recipe.viewable_by_teams.all():
        if team == signed_in.name or is_team_member(session, api, team.team, signed_in):
            return True

    if recipe.viewable_by_teams.count():
        return False

    # No viewable_by_teams was specified. They need to be
    # a collaborator on the repository
    collab = is_collaborator(session, build_user, recipe.repository, user=signed_in)
    if not collab:
        return False

    return True

def viewable_repos(session):
    """
    Gets the viewable repo IDs for the given session.

    In this case, only _active_ repos are viewable.

    Uses caching to avoid git calls for being able to see repos.
    """
    cache_key = 'viewable_repos_cache'
    cache = session.get(cache_key, [])

    timeout_key = 'viewable_repos_timeout'
    timeout = session.get(timeout_key, 0)

    # Need to regenerate
    if timeout <= TimeUtils.get_local_timestamp():
        logger.info('Rebuilding viewable repos')
        cache = []

        for server in settings.INSTALLED_GITSERVERS:
            try:
                gs = models.GitServer.objects.get(host_type=server["type"], name=server["hostname"])
            except models.GitServer.DoesNotExist: # Happens in testing
                continue

            user = gs.signed_in_user(session)
            all_repos = user.api().get_all_repos(None) if user is not None else []

            logger.info(f'Rebuilding viewable repos for user {user} on {server}')

            repos_q = models.Repository.objects.filter(active=True, user__server=gs)
            for repo in repos_q.all():
                if repo.public() or (user is not None and
                                     ((str(repo) in all_repos)
                                      or user.api().can_view_repo(repo.user.name, repo.name))):
                    cache.append(repo.id)

        session[cache_key] = cache
        session[timeout_key] = TimeUtils.get_local_timestamp() + settings.PERMISSION_CACHE_TIMEOUT

    return cache

def can_view_repo(session, repo):
    """
    Checks whether or not the given session has permissions to view the repo.
    """
    if session is None:
        return repo.public()
    return repo.id in viewable_repos(session)

def is_team_member(session, api, team, user):
    """
    Checks to see if a user is a team member and caches the results
    """
    teams = session.get("teams", {})
    # Check to see if their permissions are still valid
    if teams and team in teams and TimeUtils.get_local_timestamp() < teams[team][1]:
        return teams[team][0]

    is_member = api.is_member(team, user)
    logger.info("User '%s' member status of '%s': %s" % (user, team, is_member))
    teams[team] = (is_member, TimeUtils.get_local_timestamp() + settings.PERMISSION_CACHE_TIMEOUT)
    session["teams"] = teams
    return is_member

def is_allowed_to_see_clients(session):
    """
    Check to see if the signed in user can see client information.
    We do this by checking the "authorized_users"
    "authorized_users" can contain orgs and teams
    """
    val = session.get("allowed_to_see_clients")
    # Check to see if their permissions are still valid
    if val and TimeUtils.get_local_timestamp() < val[1]:
        return val[0]

    user = None

    for server in settings.INSTALLED_GITSERVERS:
        gitserver = models.GitServer.objects.get(host_type=server["type"], name=server["hostname"])
        auth = gitserver.auth()
        user = auth.signed_in_user(gitserver, session)
        if not user:
            continue

        api = user.api()
        for authed_user in server.get("authorized_users", []):
            if user.name == authed_user or is_team_member(session, api, authed_user, user):
                logger.info("'%s' is a member of '%s' and is allowed to see clients" % (user, authed_user))
                session["allowed_to_see_clients"] = (True,
                        TimeUtils.get_local_timestamp() + settings.PERMISSION_CACHE_TIMEOUT)
                return True
        logger.info("%s is NOT allowed to see clients on %s" % (user, gitserver))
    session["allowed_to_see_clients"] = (False, TimeUtils.get_local_timestamp() + settings.PERMISSION_CACHE_TIMEOUT)
    return False
