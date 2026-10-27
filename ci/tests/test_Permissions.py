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
from mock import patch, MagicMock
from ci import models, Permissions
from django.conf import settings
from django.core.cache import cache
from django.test import Client, override_settings
from . import utils
from ci.tests import DBTester
from requests_oauthlib import OAuth2Session


@override_settings(INSTALLED_GITSERVERS=[utils.github_config()])
class Tests(DBTester.DBTester):
    @patch.object(OAuth2Session, "get")
    @patch.object(models.GitUser, "is_admin")
    def test_is_collaborator(self, mock_is_admin, mock_get):
        with self.settings(PERMISSION_CACHE_TIMEOUT=10):
            mock_is_admin.return_value = False

            build_user = utils.create_user_with_token(name="build user")
            repo = utils.create_repo()
            user = utils.create_user(name="auth user")
            # not signed in
            session = self.client.session
            with self.assertNumQueries(0):
                allowed = Permissions.is_collaborator(session, build_user, repo)
            self.assertFalse(allowed)

            utils.simulate_login(self.client.session, user)
            session = self.client.session
            mock_get.return_value = utils.Response(
                status_code=404
            )  # not a collaborator
            allowed = Permissions.is_collaborator(session, build_user, repo)
            self.assertEqual(mock_is_admin.call_count, 1)
            self.assertIs(allowed, False)
            self.assertEqual(mock_get.call_count, 1)
            session.save()  # make sure the cache is saved

            # Now try again. The only query should be to get the signed in user
            mock_get.call_count = 0
            mock_is_admin.call_count = 0
            with self.assertNumQueries(1):
                allowed = Permissions.is_collaborator(session, build_user, repo)
            self.assertEqual(mock_is_admin.call_count, 1)
            self.assertIs(allowed, False)
            self.assertEqual(mock_get.call_count, 0)
            session.save()

            # Now try again. We pass in the user so there shouldn't be any queries
            mock_is_admin.call_count = 0
            with self.assertNumQueries(0):
                allowed = Permissions.is_collaborator(
                    session, build_user, repo, user=user
                )
            self.assertIs(allowed, False)
            self.assertEqual(mock_get.call_count, 0)
            self.assertEqual(mock_is_admin.call_count, 1)
            session.save()

            # Just to make sure, it would be allowed but we still read from the cache
            mock_get.return_value = utils.Response(status_code=204)  # is a collaborator
            mock_is_admin.call_count = 0
            with self.assertNumQueries(0):
                allowed = Permissions.is_collaborator(
                    session, build_user, repo, user=user
                )
            self.assertIs(allowed, False)
            self.assertEqual(mock_get.call_count, 0)
            self.assertEqual(mock_is_admin.call_count, 1)
            session.save()

        with self.settings(PERMISSION_CACHE_TIMEOUT=0):
            # now start over with no timeout
            session.clear()
            utils.simulate_login(session, user)
            mock_get.return_value = utils.Response(
                status_code=404
            )  # not a collaborator
            mock_get.call_count = 0

            # is an admin
            mock_is_admin.call_count = 0
            mock_is_admin.return_value = True
            allowed = Permissions.is_collaborator(session, build_user, repo, user=user)
            self.assertTrue(allowed)
            self.assertEqual(mock_is_admin.call_count, 1)
            mock_is_admin.return_value = False

            with self.assertNumQueries(0):
                allowed = Permissions.is_collaborator(
                    session, build_user, repo, user=user
                )
            self.assertIs(allowed, False)
            self.assertEqual(mock_get.call_count, 1)
            session.save()

            # and again
            mock_get.call_count = 0
            with self.assertNumQueries(0):
                allowed = Permissions.is_collaborator(
                    session, build_user, repo, user=user
                )
            self.assertIs(allowed, False)
            self.assertEqual(mock_get.call_count, 1)
            session.save()

            mock_get.return_value = utils.Response(status_code=204)  # is a collaborator
            # Should be good
            mock_get.call_count = 0
            with self.assertNumQueries(0):
                allowed = Permissions.is_collaborator(
                    session, build_user, repo, user=user
                )
            self.assertIs(allowed, True)
            self.assertEqual(mock_get.call_count, 1)
            session.save()

            mock_get.side_effect = Exception("Boom!")
            # On error, no collaborator
            mock_get.call_count = 0
            with self.assertNumQueries(0):
                allowed = Permissions.is_collaborator(
                    session, build_user, repo, user=user
                )
            self.assertIs(allowed, False)
            self.assertEqual(mock_get.call_count, 1)

    @patch.object(OAuth2Session, "get")
    @patch.object(models.GitUser, "is_admin")
    def test_has_write_access(self, mock_is_admin, mock_get):
        mock_is_admin.return_value = False
        build_user = utils.create_user_with_token(name="build user")
        repo = utils.create_repo()
        user = utils.create_user(name="auth user")

        # not signed in
        session = self.client.session
        self.assertFalse(Permissions.has_write_access(session, build_user, repo))
        self.assertEqual(mock_get.call_count, 0)

        utils.simulate_login(self.client.session, user)
        session = self.client.session

        with self.settings(PERMISSION_CACHE_TIMEOUT=10):
            # read only
            mock_get.return_value = utils.Response({"permission": "read"})
            allowed = Permissions.has_write_access(session, build_user, repo)
            self.assertIs(allowed, False)
            self.assertEqual(mock_get.call_count, 1)

            # cached
            mock_get.return_value = utils.Response({"permission": "write"})
            allowed = Permissions.has_write_access(session, build_user, repo)
            self.assertIs(allowed, False)
            self.assertEqual(mock_get.call_count, 1)

            # the collaborator cache is separate
            self.assertNotIn(user.auth()._collaborators_key, session)

        with self.settings(PERMISSION_CACHE_TIMEOUT=0):
            # start over with no timeout
            session.clear()
            utils.simulate_login(session, user)
            allowed = Permissions.has_write_access(session, build_user, repo, user=user)
            self.assertIs(allowed, True)
            self.assertEqual(mock_get.call_count, 2)

            # admins always have write access
            mock_is_admin.return_value = True
            mock_get.return_value = utils.Response({"permission": "read"})
            allowed = Permissions.has_write_access(session, build_user, repo, user=user)
            self.assertIs(allowed, True)
            self.assertEqual(mock_get.call_count, 2)

    @patch.object(Permissions, "is_collaborator")
    @patch.object(Permissions, "has_write_access")
    def test_can_invalidate(self, mock_write, mock_collab):
        mock_write.return_value = False
        mock_collab.return_value = True
        ev = utils.create_event()
        author = utils.create_user(name="pr author")
        other = utils.create_user(name="other user")
        pr = utils.create_pr()
        pr.username = author.name
        pr.save()
        ev.pull_request = pr
        ev.save()

        # not signed in
        session = self.client.session
        self.assertFalse(Permissions.can_invalidate(session, ev))
        self.assertEqual(mock_write.call_count, 0)

        # signed in user is the author and a collaborator
        utils.simulate_login(self.client.session, author)
        session = self.client.session
        self.assertTrue(Permissions.can_invalidate(session, ev))
        self.assertEqual(mock_write.call_count, 0)
        self.assertEqual(mock_collab.call_count, 1)

        # the author must also be a collaborator
        mock_collab.return_value = False
        self.assertFalse(Permissions.can_invalidate(session, ev))
        self.assertEqual(mock_write.call_count, 1)
        mock_write.return_value = True
        self.assertTrue(Permissions.can_invalidate(session, ev))
        self.assertEqual(mock_write.call_count, 2)
        mock_write.return_value = False
        mock_write.call_count = 0
        mock_collab.return_value = True
        mock_collab.call_count = 0

        # not the author and no write access, even as a collaborator
        self.assertFalse(Permissions.can_invalidate(session, ev, user=other))
        self.assertEqual(mock_write.call_count, 1)
        self.assertEqual(mock_collab.call_count, 0)

        # not the author but has write access
        mock_write.return_value = True
        self.assertTrue(Permissions.can_invalidate(session, ev, user=other))
        self.assertEqual(mock_write.call_count, 2)

        # the author is only special on pull requests
        for cause in [models.Event.PUSH, models.Event.MANUAL, models.Event.RELEASE]:
            ev.cause = cause
            ev.save()
            mock_write.return_value = False
            self.assertFalse(Permissions.can_invalidate(session, ev, user=author))
            mock_write.return_value = True
            self.assertTrue(Permissions.can_invalidate(session, ev, user=author))

        # a pull request event without a pull request needs write access
        ev.cause = models.Event.PULL_REQUEST
        ev.pull_request = None
        ev.save()
        mock_write.return_value = False
        self.assertFalse(Permissions.can_invalidate(session, ev, user=author))

    @patch.object(Permissions, "can_invalidate")
    def test_can_cancel(self, mock_invalidate):
        ev = utils.create_event()
        user = utils.create_user(name="some user")
        session = self.client.session
        for allowed in [True, False]:
            mock_invalidate.return_value = allowed
            self.assertIs(Permissions.can_cancel(session, ev, user=user), allowed)
            mock_invalidate.assert_called_with(session, ev, user=user)

    @patch.object(OAuth2Session, "get")
    def test_job_permissions(self, mock_get):
        """
        testing Permissions.job_permissions works
        """
        # not the owner and not a collaborator
        mock_get.return_value = utils.Response(status_code=404)
        job = utils.create_job()
        job.recipe.private = False
        job.recipe.save()
        session = self.client.session
        ret = Permissions.job_permissions(session, job)
        self.assertTrue(ret["can_see_results"])  # not private
        self.assertFalse(ret["can_activate"])

        # Private recipe and not a collaborator
        job.recipe.private = True
        job.recipe.save()
        session = self.client.session
        ret = Permissions.job_permissions(session, job)
        self.assertFalse(ret["can_see_results"])  # private
        self.assertFalse(ret["can_activate"])

        # user is signed in but not a collaborator
        # recipe is still private
        user = utils.get_test_user()
        utils.simulate_login(self.client.session, user)
        ret = Permissions.job_permissions(session, job)
        self.assertFalse(ret["can_see_results"])
        self.assertFalse(ret["can_activate"])
        self.assertFalse(ret["can_invalidate"])
        self.assertFalse(ret["can_cancel"])

        # user is the author of the pull request but not a collaborator
        pr = utils.create_pr()
        pr.username = user.name
        pr.save()
        job.event.pull_request = pr
        job.event.save()
        session = self.client.session
        ret = Permissions.job_permissions(session, job)
        self.assertFalse(ret["can_invalidate"])
        self.assertFalse(ret["can_cancel"])

        # user is the author of the pull request and a collaborator
        mock_get.return_value = utils.Response(status_code=204)
        session = self.client.session
        ret = Permissions.job_permissions(session, job)
        self.assertFalse(ret["can_activate"])
        self.assertTrue(ret["can_invalidate"])
        self.assertTrue(ret["can_cancel"])
        mock_get.return_value = utils.Response(status_code=404)
        job.event.pull_request = None
        job.event.save()

        # user is a collaborator now, but without write access
        mock_get.return_value = utils.Response(status_code=204)
        session = self.client.session
        ret = Permissions.job_permissions(session, job)
        self.assertTrue(ret["can_see_results"])
        self.assertFalse(ret["can_activate"])

        # user is a collaborator and the recipe is not private
        job.recipe.private = False
        job.recipe.save()
        session = self.client.session
        ret = Permissions.job_permissions(session, job)
        self.assertTrue(ret["can_see_results"])
        self.assertFalse(ret["can_activate"])

        job.recipe.private = True
        job.recipe.save()
        # manual recipe. a collaborator can't activate
        job.recipe.automatic = models.Recipe.MANUAL
        job.recipe.save()
        session = self.client.session
        ret = Permissions.job_permissions(session, job)
        self.assertTrue(ret["can_see_results"])
        self.assertFalse(ret["can_activate"])

        # auto authorized recipe. being auto authorized doesn't
        # allow manually activating
        job.recipe.automatic = models.Recipe.AUTO_FOR_AUTHORIZED
        job.recipe.auto_authorized.add(user)
        job.recipe.save()
        ret = Permissions.job_permissions(session, job)
        self.assertTrue(ret["can_see_results"])
        self.assertFalse(ret["can_activate"])

        # write access, but can't see the private recipe
        session = self.client.session
        mock_get.return_value = utils.Response({"permission": "write"})
        ret = Permissions.job_permissions(session, job)
        self.assertFalse(ret["can_see_results"])
        self.assertFalse(ret["can_activate"])
        self.assertFalse(ret["can_invalidate"])
        self.assertFalse(ret["can_cancel"])

        # write access can activate
        job.recipe.private = False
        job.recipe.save()
        session = self.client.session
        ret = Permissions.job_permissions(session, job)
        self.assertTrue(ret["can_activate"])
        self.assertTrue(ret["can_invalidate"])
        self.assertTrue(ret["can_cancel"])

        # there was an exception somewhere
        job.recipe.private = True
        job.recipe.save()
        session = self.client.session
        mock_get.side_effect = Exception("Boom!")
        ret = Permissions.job_permissions(session, job)
        self.assertFalse(ret["can_see_results"])
        self.assertFalse(ret["can_activate"])

    @patch.object(Permissions, "is_team_member")
    @patch.object(Permissions, "is_collaborator")
    @patch.object(Permissions, "has_write_access")
    def test_job_permissions_teams(self, mock_write, mock_collab, mock_member):
        """
        Collaborators with write access that aren't on a team that can view
        a private recipe can't change its jobs
        """
        mock_write.return_value = True
        mock_collab.return_value = True
        mock_member.return_value = False
        job = utils.create_job()
        job.recipe.private = True
        job.recipe.save()
        models.RecipeViewableByTeam.objects.create(team="foo", recipe=job.recipe)
        user = utils.create_user_with_token(name="some user")
        utils.simulate_login(self.client.session, user)

        keys = ["can_see_results", "can_activate"]
        keys += ["can_invalidate", "can_cancel"]
        session = self.client.session
        ret = Permissions.job_permissions(session, job)
        for key in keys:
            self.assertFalse(ret[key], key)

        mock_member.return_value = True
        session = self.client.session
        ret = Permissions.job_permissions(session, job)
        for key in keys:
            self.assertTrue(ret[key], key)

    @patch.object(Permissions, "can_see_results")
    def test_can_see_event_results(self, mock_see):
        job = utils.create_job()
        job.recipe.private = True
        job.recipe.save()
        public = utils.create_recipe(name="public")
        public.private = False
        public.save()
        utils.create_job(recipe=public, event=job.event)
        session = self.client.session

        # Only private recipes are checked
        for allowed in [True, False]:
            mock_see.return_value = allowed
            mock_see.reset_mock()
            self.assertIs(
                Permissions.can_see_event_results(session, job.event), allowed
            )
            mock_see.assert_called_once_with(session, job.recipe)

        # No private recipes
        job.recipe.private = False
        job.recipe.save()
        mock_see.reset_mock()
        self.assertTrue(Permissions.can_see_event_results(session, job.event))
        mock_see.assert_not_called()

    def test_can_manage_clients(self):
        user = utils.create_user(name="admin user")
        # not signed in
        session = self.client.session
        self.assertFalse(Permissions.can_manage_clients(session))
        self.assertIsNone(Permissions.client_manager(session))

        # signed in, not an admin
        utils.simulate_login(self.client.session, user)
        session = self.client.session
        self.assertFalse(Permissions.can_manage_clients(session))
        self.assertIsNone(Permissions.client_manager(session))

        # signed in admin
        config = utils.github_config()
        config["admins"] = [user.name]
        with self.settings(INSTALLED_GITSERVERS=[config]):
            self.assertTrue(Permissions.can_manage_clients(session))
            self.assertEqual(Permissions.client_manager(session), user)

    def test_missing_server(self):
        """
        A configured server without a matching database entry is skipped
        """
        config = utils.github_config()
        config["hostname"] = "no_such_server"
        with self.settings(INSTALLED_GITSERVERS=[config]):
            session = self.client.session
            self.assertFalse(Permissions.is_allowed_to_see_clients(session))
            self.assertIsNone(Permissions.client_manager(session))
            self.assertFalse(Permissions.can_manage_clients(session))

    @patch.object(OAuth2Session, "get")
    def test_is_allowed_to_see_clients(self, mock_get):
        user = utils.create_user(name="auth user")
        build_user = utils.create_recipe().build_user
        with self.settings(
            INSTALLED_GITSERVERS=[utils.github_config(authorized_users=["team"])]
        ):
            # not signed in
            session = self.client.session
            with self.assertNumQueries(1):
                allowed = Permissions.is_allowed_to_see_clients(session)
            self.assertFalse(allowed)

            utils.simulate_login(self.client.session, user)
            session = self.client.session
            # A signed in user, shouldn't match authorized_users
            mock_get.return_value = utils.Response(status_code=404)
            with patch.object(
                models.GitUser, "api", autospec=True, side_effect=models.GitUser.api
            ) as mock_api:
                # 1 more to find the build user
                with self.assertNumQueries(4):
                    allowed = Permissions.is_allowed_to_see_clients(session)
            self.assertFalse(allowed)
            self.assertEqual(mock_get.call_count, 1)
            # Checked as the build user
            mock_api.assert_called_once_with(build_user)
            self.assertIn("/orgs/team/members/auth%20user", mock_get.call_args[0][0])
            session.save()

            # This time it should hit cache
            with self.assertNumQueries(0):
                allowed = Permissions.is_allowed_to_see_clients(session)
            self.assertFalse(allowed)
            self.assertEqual(mock_get.call_count, 1)

            # Clear the cache and try the success route
        with self.settings(
            INSTALLED_GITSERVERS=[utils.github_config(authorized_users=[user.name])]
        ):
            utils.simulate_login(self.client.session, user)
            session = self.client.session
            mock_get.return_value = utils.Response(status_code=204)

            with self.assertNumQueries(3):
                allowed = Permissions.is_allowed_to_see_clients(session)
            self.assertTrue(allowed)
            self.assertEqual(
                mock_get.call_count, 1
            )  # team is the same as user name so no call
            session.save()

            # Should hit cache
            with self.assertNumQueries(0):
                allowed = Permissions.is_allowed_to_see_clients(session)
            self.assertTrue(allowed)
            self.assertEqual(mock_get.call_count, 1)

    @patch.object(OAuth2Session, "get")
    def test_is_allowed_to_see_clients_build_user(self, mock_get):
        """
        The membership in authorized_users is checked as the build user
        named by authorized_users_build_user, else the first build user
        """
        user = utils.create_user(name="auth user")
        utils.simulate_login(self.client.session, user)
        mock_get.return_value = utils.Response(status_code=204)
        config = utils.github_config(authorized_users=["team"])

        # No build user to check with
        with self.settings(INSTALLED_GITSERVERS=[config]):
            self.assertFalse(Permissions.is_allowed_to_see_clients(self.client.session))
        self.assertEqual(mock_get.call_count, 0)

        # Users named directly don't need a build user, wherever they are listed
        named = utils.github_config(authorized_users=["team", user.name])
        with self.settings(INSTALLED_GITSERVERS=[named]):
            utils.simulate_login(self.client.session, user)
            self.assertTrue(Permissions.is_allowed_to_see_clients(self.client.session))
        self.assertEqual(mock_get.call_count, 0)
        utils.simulate_login(self.client.session, user)

        # Users with tokens that aren't build users aren't used
        server = user.server
        utils.create_user_with_token(name="a user", server=server)
        self.assertIsNone(Permissions.clients_build_user(server))

        b_user = utils.create_user_with_token(name="b build user", server=server)
        utils.create_webhook(build_user=b_user)
        c_user = utils.create_user_with_token(name="c build user", server=server)
        utils.create_recipe(user=c_user)
        with self.settings(INSTALLED_GITSERVERS=[config]):
            self.assertEqual(Permissions.clients_build_user(server), b_user)
            self.assertTrue(Permissions.is_allowed_to_see_clients(self.client.session))
        self.assertEqual(mock_get.call_count, 1)

        config["authorized_users_build_user"] = c_user.name
        with self.settings(INSTALLED_GITSERVERS=[config]):
            self.assertEqual(Permissions.clients_build_user(server), c_user)

            # The named user is only used if they have a token
            c_user.token = ""
            c_user.save()
            self.assertIsNone(Permissions.clients_build_user(server))

    @patch.object(OAuth2Session, "get")
    def test_is_team_member(self, mock_get):
        user = utils.create_user(name="auth user")
        api = user.api()
        mock_get.return_value = utils.Response()
        session = self.client.session
        # Not a member
        is_member = Permissions.is_team_member(session, api, "team", user)
        self.assertFalse(is_member)
        self.assertEqual(mock_get.call_count, 1)

        # Should be cached
        is_member = Permissions.is_team_member(session, api, "team", user)
        self.assertFalse(is_member)
        self.assertEqual(mock_get.call_count, 1)

        session = self.client.session  # clears the cache
        # A member
        is_member = Permissions.is_team_member(session, api, user.name, user)
        self.assertTrue(is_member)
        self.assertEqual(
            mock_get.call_count, 1
        )  # team is the same as user name so no call

        # Should be cached
        is_member = Permissions.is_team_member(session, api, user.name, user)
        self.assertTrue(is_member)
        self.assertEqual(mock_get.call_count, 1)

    def test_is_team_member_per_server(self):
        # The same team name on two servers must not share a cache entry
        github_user = utils.create_user(name="auth user")
        gitlab_server = utils.create_git_server(
            name="gitlab_server", host_type=settings.GITSERVER_GITLAB
        )
        gitlab_user = utils.create_user(name="auth user", server=gitlab_server)
        github_api = MagicMock()
        github_api.is_member.return_value = True
        gitlab_api = MagicMock()
        gitlab_api.is_member.return_value = False
        session = self.client.session

        self.assertTrue(
            Permissions.is_team_member(session, github_api, "team", github_user)
        )
        # Not served from the GitHub cache entry, so it asks GitLab
        self.assertFalse(
            Permissions.is_team_member(session, gitlab_api, "team", gitlab_user)
        )
        self.assertEqual(github_api.is_member.call_count, 1)
        self.assertEqual(gitlab_api.is_member.call_count, 1)

        # Both are cached independently
        self.assertTrue(
            Permissions.is_team_member(session, github_api, "team", github_user)
        )
        self.assertFalse(
            Permissions.is_team_member(session, gitlab_api, "team", gitlab_user)
        )
        self.assertEqual(github_api.is_member.call_count, 1)
        self.assertEqual(gitlab_api.is_member.call_count, 1)

    @patch.object(OAuth2Session, "get")
    def test_can_see_results_team_is_user(self, mock_get):
        """
        A viewable_by_teams entry that matches the signed in user's name
        grants access without asking the remote server about team membership
        """
        recipe = utils.create_recipe()
        recipe.private = True
        recipe.save()
        user = utils.create_user(name="some user")
        models.RecipeViewableByTeam.objects.create(team=user.name, recipe=recipe)
        utils.simulate_login(self.client.session, user)
        session = self.client.session
        self.assertTrue(Permissions.can_see_results(session, recipe))
        self.assertEqual(mock_get.call_count, 0)

    @patch.object(OAuth2Session, "get")
    def test_can_see_results(self, mock_get):
        recipe = utils.create_recipe()
        mock_get.return_value = utils.Response(status_code=404)  # not a collaborator

        session = self.client.session

        # Recipe isn't private, everybody can see it, even
        # when not signed in
        recipe.private = False
        recipe.save()
        ret = Permissions.can_see_results(session, recipe)
        self.assertTrue(ret)
        self.assertEqual(mock_get.call_count, 0)

        # Recipe is private, not signed in users can't see it
        recipe.private = True
        recipe.save()
        ret = Permissions.can_see_results(session, recipe)
        self.assertFalse(ret)
        self.assertEqual(mock_get.call_count, 0)

        # The build_user should always be able to see results
        utils.simulate_login(self.client.session, recipe.build_user)
        session = self.client.session
        ret = Permissions.can_see_results(session, recipe)
        self.assertTrue(ret)
        self.assertEqual(mock_get.call_count, 0)

        # A normal user that isn't a collaborator
        user = utils.create_user(name="some user")
        utils.simulate_login(self.client.session, user)
        session = self.client.session
        ret = Permissions.can_see_results(session, recipe)
        self.assertFalse(ret)
        self.assertEqual(mock_get.call_count, 1)

        # A normal user that is a collaborator
        session = self.client.session  # so we don't hit the cache
        mock_get.return_value = utils.Response(status_code=204)  # a collaborator
        mock_get.call_count = 0
        ret = Permissions.can_see_results(session, recipe)
        self.assertTrue(ret)
        self.assertEqual(mock_get.call_count, 1)

        # Again, to test the cache
        mock_get.call_count = 0
        ret = Permissions.can_see_results(session, recipe)
        self.assertTrue(ret)
        self.assertEqual(mock_get.call_count, 0)

        # Now try with teams
        session = self.client.session  # so we don't hit the cache
        mock_get.return_value = utils.Response(status_code=404)
        models.RecipeViewableByTeam.objects.create(team="foo", recipe=recipe)

        # Not a member of the team
        ret = Permissions.can_see_results(session, recipe)
        self.assertFalse(ret)
        self.assertEqual(mock_get.call_count, 1)

        # Again, to test the cache
        mock_get.call_count = 0
        ret = Permissions.can_see_results(session, recipe)
        self.assertFalse(ret)
        self.assertEqual(mock_get.call_count, 0)

        # A valid member of the team, checked as the build user
        session = self.client.session  # clear the cache
        mock_get.return_value = utils.Response(status_code=204)
        with patch.object(
            models.GitUser, "api", autospec=True, side_effect=models.GitUser.api
        ) as mock_api:
            ret = Permissions.can_see_results(session, recipe)
        self.assertTrue(ret)
        self.assertEqual(mock_get.call_count, 1)
        self.assertIn("/orgs/foo/members/some%20user", mock_get.call_args[0][0])
        mock_api.assert_called_once_with(recipe.build_user)

        # Again, to test the cache
        mock_get.call_count = 0
        ret = Permissions.can_see_results(session, recipe)
        self.assertTrue(ret)
        self.assertEqual(mock_get.call_count, 0)

    def test_anonymous_session_not_modified(self):
        """
        Checking permissions without a signed in user shouldn't write to
        the session, otherwise every anonymous request would store a session
        """
        repo = utils.create_repo(active=True)
        session = self.client.session
        # Creating the test client session marks it modified
        session.modified = False
        with patch.object(models.Repository, "public") as mock_public:
            mock_public.return_value = True
            self.assertEqual(Permissions.viewable_repos(session), [repo.id])
            self.assertTrue(Permissions.can_view_repo(session, repo))
        self.assertFalse(Permissions.is_allowed_to_see_clients(session))
        self.assertFalse(session.modified)
        self.assertEqual(dict(session), {})

    def test_signed_in_session_cached(self):
        """
        Checking permissions with a signed in user caches the results
        """
        user = utils.create_user_with_token()
        utils.simulate_login(self.client.session, user)
        session = self.client.session
        Permissions.viewable_repos(session)
        Permissions.is_allowed_to_see_clients(session)
        self.assertIn("viewable_repos_cache", session)
        self.assertIn("allowed_to_see_clients", session)

    def test_viewable_repos_queries(self):
        """
        The number of queries to build the viewable repos doesn't depend
        on the number of repos, and the public repos are shared between
        anonymous sessions
        """
        owner = utils.create_user(name="owner")
        repo = utils.create_repo(name="repo0", user=owner, active=True)

        # The test client sessions are created (and saved) when accessed
        session = self.client.session
        other_session = Client().session

        # 1 for the GitServer, 1 for the repos (with their user and server)
        with self.assertNumQueries(2):
            self.assertEqual(Permissions.viewable_repos(session), [repo.id])

        # Cached, even for a different anonymous session
        repos = [repo] + [
            utils.create_repo(name=f"repo{i}", user=owner, active=True)
            for i in range(1, 10)
        ]
        with self.assertNumQueries(1):
            self.assertEqual(Permissions.viewable_repos(other_session), [repo.id])

        # Rebuilt once the cache expires, still without a query per repo
        cache.delete(Permissions.PUBLIC_REPOS_CACHE_KEY)
        with self.assertNumQueries(2):
            self.assertEqual(Permissions.viewable_repos(session), [r.id for r in repos])

    @patch.object(Permissions, "is_collaborator")
    def test_viewable_repos_signed_in(self, mock_collab):
        """
        A signed in user can see the public repos and the private repos
        that they are a collaborator on, checked as the repo's build user
        """
        owner = utils.create_user(name="owner")
        public = utils.create_repo(name="public", user=owner, active=True)
        private = utils.create_repo(name="private", user=owner, active=True)
        hidden = utils.create_repo(name="hidden", user=owner, active=True)
        # Without a build user, nobody but admins can see it
        no_build_user = utils.create_repo(name="no build", user=owner, active=True)
        build_user = utils.create_user_with_token(name="build user")
        webhook_user = utils.create_user_with_token(name="webhook user")
        utils.create_recipe(user=build_user, repo=private)
        utils.create_webhook(repo=private, build_user=webhook_user)
        utils.create_webhook(repo=hidden, build_user=webhook_user)
        user = utils.create_user_with_token(name="signed in")
        utils.simulate_login(self.client.session, user)

        def is_collaborator(session, build_user, repo, user=None):
            return repo == private

        mock_collab.side_effect = is_collaborator

        def public_repo(repo):
            return repo == public

        session = self.client.session
        with patch.object(models.Repository, "public", autospec=True) as mock_public:
            mock_public.side_effect = public_repo
            repos = Permissions.viewable_repos(session)
        self.assertCountEqual(repos, [public.id, private.id])
        self.assertNotIn(hidden.id, repos)
        self.assertNotIn(no_build_user.id, repos)
        # Checked as the recipe's build user, else the webhook's
        self.assertCountEqual(
            [(c.args[1], c.args[2]) for c in mock_collab.call_args_list],
            [(build_user, private), (webhook_user, hidden)],
        )
        for c in mock_collab.call_args_list:
            self.assertEqual(c.kwargs["user"], user)

        # Admins can see everything
        session = self.client.session
        with patch.object(models.GitUser, "is_admin") as mock_is_admin:
            mock_is_admin.return_value = True
            with patch.object(models.Repository, "public") as mock_public:
                mock_public.return_value = False
                repos = Permissions.viewable_repos(session)
        self.assertCountEqual(
            repos, [public.id, private.id, hidden.id, no_build_user.id]
        )
