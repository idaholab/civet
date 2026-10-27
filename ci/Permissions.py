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
import logging
from ci import models, TimeUtils
from django.conf import settings
from django.core.cache import cache as django_cache
from django.db.models import Q

logger = logging.getLogger("ci")


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
      bool: whether the user is a collaborator
    """
    server = repo.server()
    if not user:
        user = server.signed_in_user(request_session)
    if not user:
        return False
    if user.is_admin():
        return True

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
    collab_dict[str(repo)] = (
        val,
        TimeUtils.get_local_timestamp() + settings.PERMISSION_CACHE_TIMEOUT,
    )
    request_session[auth._collaborators_key] = collab_dict
    logger.info("Is collaborator for user '%s' on %s: %s" % (user, repo, val))
    return val


def has_write_access(request_session, build_user, repo, user=None):
    """
    Checks to see if the signed in user has write access to a repo.
    This will cache the value for a time specified by settings.PERMISSION_CACHE_TIMEOUT
    Input:
      request_session: A session from HttpRequest.session
      build_user: models.GitUser who has access to check permissions
      repo: models.Repository to check against
      user: models.GitUser: User to check for. If None then the user will be pulled from the request_session
    Return:
      bool: Whether the user has write access
    """
    server = repo.server()
    if not user:
        user = server.signed_in_user(request_session)
    if not user:
        return False
    if user.is_admin():
        return True

    key = server.auth()._write_access_key
    write_dict = request_session.get(key, {})
    val = write_dict.get(str(repo))
    # Check to see if their permissions are still valid
    if val and TimeUtils.get_local_timestamp() < val[1]:
        return val[0]

    val = build_user.api().has_write_access(user, repo)
    write_dict[str(repo)] = (
        val,
        TimeUtils.get_local_timestamp() + settings.PERMISSION_CACHE_TIMEOUT,
    )
    request_session[key] = write_dict
    logger.info("Has write access for user '%s' on %s: %s" % (user, repo, val))
    return val


def can_invalidate(session, event, user=None):
    """
    Checks to see if the signed in user can invalidate the jobs on an event.
    Users with write access can invalidate any event. The author of a
    pull request can also invalidate the events on their pull request
    if they are a collaborator.
    Input:
      session: A session from HttpRequest.session
      event: models.Event to check against
      user: models.GitUser: User to check for. If None then the user will be pulled from the session
    Return:
      bool: Whether the user can invalidate
    """
    if not user:
        user = event.base.server().signed_in_user(session)
    if not user:
        return False

    repo = event.base.repo()
    if (
        event.cause == models.Event.PULL_REQUEST
        and event.pull_request
        and event.pull_request.username == user.name
        and is_collaborator(session, event.build_user, repo, user=user)
    ):
        return True

    return has_write_access(session, event.build_user, repo, user=user)


def can_cancel(session, event, user=None):
    """
    Checks to see if the signed in user can cancel the jobs on an event.
    This uses the same rules as can_invalidate().
    Input:
      session: A session from HttpRequest.session
      event: models.Event to check against
      user: models.GitUser: User to check for. If None then the user will be pulled from the session
    Return:
      bool: Whether the user can cancel
    """
    return can_invalidate(session, event, user=user)


def job_permissions(session, job):
    """
    Logic for a job to see who can see results, activate,
    cancel, or invalidate the job.
    """
    ret_dict = {
        "can_prioritize": False,
        "can_see_results": False,
        "can_activate": False,
        "can_invalidate": False,
        "can_cancel": False,
        "can_see_client": False,
    }
    server = job.event.base.server()
    repo = job.recipe.repository
    user = server.signed_in_user(session)
    admin = is_server_admin(session, server)

    ret_dict["can_see_client"] = is_allowed_to_see_clients(session)
    ret_dict["can_prioritize"] = admin

    if user == job.recipe.build_user or admin:
        # The owner should be able to do everything
        ret_dict["can_see_results"] = True
        ret_dict["can_activate"] = True
        ret_dict["can_invalidate"] = True
        ret_dict["can_cancel"] = True
        return ret_dict

    ret_dict["can_see_results"] = can_see_results(session, job.recipe)

    if not user:
        return ret_dict

    if job.recipe.private and not ret_dict["can_see_results"]:
        # Users that can't see a private recipe can't change its jobs either
        return ret_dict

    ret_dict["can_invalidate"] = can_invalidate(session, job.event, user=user)
    ret_dict["can_cancel"] = can_cancel(session, job.event, user=user)

    ret_dict["can_activate"] = has_write_access(
        session, job.event.build_user, repo, user=user
    )
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

    if not signed_in:
        return False

    if signed_in == build_user or signed_in.is_admin():
        return True

    # The signed in user's token can only identify them, so check
    # membership as the build user
    api = build_user.api()

    # if viewable_by_teams was specified we check if
    # the signed in user is a member of one of the teams
    for team in recipe.viewable_by_teams.all():
        if team.team == signed_in.name or is_team_member(
            session, api, team.team, signed_in
        ):
            return True

    if recipe.viewable_by_teams.count():
        return False

    # No viewable_by_teams was specified. They need to be
    # a collaborator on the repository
    collab = is_collaborator(session, build_user, recipe.repository, user=signed_in)
    if not collab:
        return False

    return True


def can_see_event_results(session, event):
    """
    Checks to see if the signed in user can see the results of
    every job on an event.
    Input:
      session: A session from HttpRequest.session
      event: models.Event to check against
    Return:
      bool: Whether the user can see the results of all jobs
    """
    recipes = models.Recipe.objects.filter(jobs__event=event, private=True)
    for recipe in recipes.distinct():
        if not can_see_results(session, recipe):
            return False
    return True


def viewable_repos(session):
    """
    Gets the viewable repo IDs for the given session.

    In this case, only _active_ repos are viewable.

    Uses caching to avoid git calls for being able to see repos.
    """
    cache_key = "viewable_repos_cache"
    cache = session.get(cache_key, [])

    timeout_key = "viewable_repos_timeout"
    timeout = session.get(timeout_key, 0)

    # Need to regenerate
    if timeout <= TimeUtils.get_local_timestamp():
        logger.debug("Rebuilding viewable repos")
        cache = []
        signed_in = False

        for server in settings.INSTALLED_GITSERVERS:
            try:
                gs = models.GitServer.objects.get(
                    host_type=server["type"], name=server["hostname"]
                )
            except models.GitServer.DoesNotExist:  # Happens in testing
                continue

            user = gs.signed_in_user(session)
            if user is None:
                cache.extend(public_repos(gs))
                continue
            signed_in = True

            is_admin = user.is_admin()
            repos = active_repos(gs)
            build_users = {} if is_admin else repo_build_users(repos)

            logger.debug(f"Rebuilding viewable repos for user {user} on {gs}")

            for repo in repos:
                if is_admin or repo.public():
                    cache.append(repo.id)
                    continue
                # The signed in user's token can only identify them, so
                # check access to private repos as their build user
                build_user = build_users.get(repo.id)
                if build_user and is_collaborator(session, build_user, repo, user=user):
                    cache.append(repo.id)

        # Without a signed in user the viewable repos are just the public
        # ones, so don't cache them; writing to the session would store a
        # new session for every anonymous request (crawlers, etc)
        if signed_in:
            session[cache_key] = cache
            session[timeout_key] = (
                TimeUtils.get_local_timestamp() + settings.PERMISSION_CACHE_TIMEOUT
            )

    return cache


def active_repos(server):
    """
    Gets the active repos on the given GitServer.
    """
    return models.Repository.objects.filter(
        active=True, user__server=server
    ).select_related("user__server")


def repo_build_users(repos):
    """
    Gets a build user with a stored token for each of the repos, to
    check access to them with. Uses the build user of a current recipe,
    else the one of a webhook.
    Return:
      dict: models.GitUser by repo ID, for the repos that have one
    """
    build_users = {}
    for model in [models.RepositoryWebhook, models.Recipe]:
        objs = model.objects.filter(repository__in=repos).exclude(build_user__token="")
        if model is models.Recipe:
            objs = objs.filter(current=True)
        objs = objs.select_related("build_user__server").order_by("-pk")
        # Later entries win, so recipes override webhooks and the
        # oldest recipe is used
        for obj in objs:
            build_users[obj.repository_id] = obj.build_user
    return build_users


def clients_build_user(gitserver):
    """
    Gets the build user to check the "authorized_users" of a server with.
    That is the user named by the server's "authorized_users_build_user"
    setting, else the first build user on the server with a stored token.
    Return:
      models.GitUser or None if there isn't one
    """
    users = (
        models.GitUser.objects.filter(server=gitserver)
        .exclude(token="")
        .select_related("server")
    )
    name = gitserver.server_config().get("authorized_users_build_user")
    if name:
        user = users.filter(name=name).first()
        if user is None:
            logger.warning(
                'authorized_users_build_user "%s" on %s has no stored token'
                % (name, gitserver)
            )
        return user
    return (
        users.filter(Q(recipes__isnull=False) | Q(webhooks__isnull=False))
        .distinct()
        .order_by("name")
        .first()
    )


# Cache key for the public repos, by GitServer ID
PUBLIC_REPOS_CACHE_KEY = "public_repos"


def public_repos(server):
    """
    Gets the IDs of the active public repos on the given GitServer.

    These are the same for every user, so they are shared through the
    cache instead of each session building them.
    """
    cached = django_cache.get(PUBLIC_REPOS_CACHE_KEY, {})
    if server.pk not in cached:
        cached[server.pk] = [repo.id for repo in active_repos(server) if repo.public()]
        # Never cache for longer than the permissions of signed in users
        timeout = min(
            settings.PUBLIC_REPOS_CACHE_TIMEOUT, settings.PERMISSION_CACHE_TIMEOUT
        )
        django_cache.set(PUBLIC_REPOS_CACHE_KEY, cached, timeout)
    return cached[server.pk]


def can_view_repo(session, repo):
    """
    Checks whether or not the given session has permissions to view the repo.
    """
    return repo.id in viewable_repos(session)


def is_team_member(session, api, team, user):
    """
    Checks to see if a user is a team member and caches the results

    The cache is keyed by server as well as team, since the same team
    name can exist on different servers (GitHub org vs GitLab group).
    """
    teams = session.get("teams", {})
    key = "%s:%s" % (user.server.pk, team)
    # Check to see if their permissions are still valid
    if teams and key in teams and TimeUtils.get_local_timestamp() < teams[key][1]:
        return teams[key][0]

    is_member = api.is_member(team, user)
    logger.info("User '%s' member status of '%s': %s" % (user, team, is_member))
    teams[key] = (
        is_member,
        TimeUtils.get_local_timestamp() + settings.PERMISSION_CACHE_TIMEOUT,
    )
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
    signed_in = False

    for server in settings.INSTALLED_GITSERVERS:
        try:
            gitserver = models.GitServer.objects.get(
                host_type=server["type"], name=server["hostname"]
            )
        except models.GitServer.DoesNotExist:  # Happens in testing
            continue
        auth = gitserver.auth()
        user = auth.signed_in_user(gitserver, session)
        if not user:
            continue
        signed_in = True

        authorized_users = server.get("authorized_users", [])
        teams = [team for team in authorized_users if team != user.name]
        is_member = len(teams) < len(authorized_users)
        if not is_member and teams:
            # The signed in user's token can only identify them, so check
            # membership as a build user
            build_user = clients_build_user(gitserver)
            if build_user is None:
                logger.warning(
                    "No build user to check authorized_users on %s" % gitserver
                )
            else:
                api = build_user.api()
                is_member = any(
                    is_team_member(session, api, team, user) for team in teams
                )
        if is_member:
            logger.info("'%s' is allowed to see clients on %s" % (user, gitserver))
            session["allowed_to_see_clients"] = (
                True,
                TimeUtils.get_local_timestamp() + settings.PERMISSION_CACHE_TIMEOUT,
            )
            return True
        logger.info("%s is NOT allowed to see clients on %s" % (user, gitserver))
    # Don't cache the answer for anonymous users; writing to the session
    # would store a new session for every anonymous request (crawlers, etc)
    if not signed_in:
        return False
    session["allowed_to_see_clients"] = (
        False,
        TimeUtils.get_local_timestamp() + settings.PERMISSION_CACHE_TIMEOUT,
    )
    return False


def is_server_admin(session, server):
    """
    Checks whether or not the user in the current session
    is an admin on the given GitServer.
    """
    user = server.signed_in_user(session)
    return user is not None and user.is_admin()


def client_manager(session):
    """
    Returns the signed in user that is an admin on any installed
    GitServer, or None. Only these users can disable or enable clients.
    """
    for server in settings.INSTALLED_GITSERVERS:
        try:
            gitserver = models.GitServer.objects.get(
                host_type=server["type"], name=server["hostname"]
            )
        except models.GitServer.DoesNotExist:  # Happens in testing
            continue
        if is_server_admin(session, gitserver):
            return gitserver.signed_in_user(session)
    return None


def can_manage_clients(session):
    """
    True if the signed in user is an admin on any installed GitServer.
    """
    return client_manager(session) is not None
