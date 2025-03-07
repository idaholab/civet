
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
from mock import patch
from ci import models, Permissions
from django.test import override_settings
from . import utils
from ci.tests import DBTester
from requests_oauthlib import OAuth2Session

@override_settings(INSTALLED_GITSERVERS=[utils.github_config()])
class Tests(DBTester.DBTester):
    @patch.object(OAuth2Session, 'get')
    def test_is_collaborator(self, mock_get):
        with self.settings(PERMISSION_CACHE_TIMEOUT=10):
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
            mock_get.return_value = utils.Response(status_code=404) # not a collaborator
            allowed = Permissions.is_collaborator(session, build_user, repo)
            self.assertIs(allowed, False)
            self.assertEqual(mock_get.call_count, 1)
            session.save() # make sure the cache is saved

            # Now try again. The only query should be to get the signed in user
            mock_get.call_count = 0
            with self.assertNumQueries(1):
                allowed = Permissions.is_collaborator(session, build_user, repo)
            self.assertIs(allowed, False)
            self.assertEqual(mock_get.call_count, 0)
            session.save()

            # Now try again. We pass in the user so there shouldn't be any queries
            with self.assertNumQueries(0):
                allowed = Permissions.is_collaborator(session, build_user, repo, user=user)
            self.assertIs(allowed, False)
            self.assertEqual(mock_get.call_count, 0)
            session.save()

            # Just to make sure, it would be allowed but we still read from the cache
            mock_get.return_value = utils.Response(status_code=204) # is a collaborator
            with self.assertNumQueries(0):
                allowed = Permissions.is_collaborator(session, build_user, repo, user=user)
            self.assertIs(allowed, False)
            self.assertEqual(mock_get.call_count, 0)
            session.save()

        with self.settings(PERMISSION_CACHE_TIMEOUT=0):
            # now start over with no timeout
            session.clear()
            utils.simulate_login(session, user)
            mock_get.return_value = utils.Response(status_code=404) # not a collaborator
            mock_get.call_count = 0

            with self.assertNumQueries(0):
                allowed = Permissions.is_collaborator(session, build_user, repo, user=user)
            self.assertIs(allowed, False)
            self.assertEqual(mock_get.call_count, 1)
            session.save()

            # and again
            mock_get.call_count = 0
            with self.assertNumQueries(0):
                allowed = Permissions.is_collaborator(session, build_user, repo, user=user)
            self.assertIs(allowed, False)
            self.assertEqual(mock_get.call_count, 1)
            session.save()

            mock_get.return_value = utils.Response(status_code=204) # is a collaborator
            # Should be good
            mock_get.call_count = 0
            with self.assertNumQueries(0):
                allowed = Permissions.is_collaborator(session, build_user, repo, user=user)
            self.assertIs(allowed, True)
            self.assertEqual(mock_get.call_count, 1)
            session.save()

            mock_get.side_effect = Exception("Boom!")
            # On error, no collaborator
            mock_get.call_count = 0
            with self.assertNumQueries(0):
                allowed = Permissions.is_collaborator(session, build_user, repo, user=user)
            self.assertIs(allowed, False)
            self.assertEqual(mock_get.call_count, 1)

    @patch.object(OAuth2Session, 'get')
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
        self.assertFalse(ret['is_owner'])
        self.assertTrue(ret['can_see_results']) # not private
        self.assertFalse(ret['can_admin'])
        self.assertFalse(ret['can_activate'])

        # Private recipe and not a collaborator
        job.recipe.private = True
        job.recipe.save()
        session = self.client.session
        ret = Permissions.job_permissions(session, job)
        self.assertFalse(ret['is_owner'])
        self.assertFalse(ret['can_see_results']) # private
        self.assertFalse(ret['can_admin'])
        self.assertFalse(ret['can_activate'])

        # user is signed in but not a collaborator
        # recipe is still private
        user = utils.get_test_user()
        utils.simulate_login(self.client.session, user)
        ret = Permissions.job_permissions(session, job)
        self.assertFalse(ret['is_owner'])
        self.assertFalse(ret['can_see_results'])
        self.assertFalse(ret['can_admin'])
        self.assertFalse(ret['can_activate'])

        # user is a collaborator now
        mock_get.return_value = utils.Response(status_code=204)
        session = self.client.session
        ret = Permissions.job_permissions(session, job)
        self.assertFalse(ret['is_owner'])
        self.assertTrue(ret['can_see_results'])
        self.assertTrue(ret['can_admin'])
        self.assertTrue(ret['can_activate'])

        # user is a collaborator and the recipe is not private
        job.recipe.private = False
        job.recipe.save()
        session = self.client.session
        ret = Permissions.job_permissions(session, job)
        self.assertFalse(ret['is_owner'])
        self.assertTrue(ret['can_see_results'])
        self.assertTrue(ret['can_admin'])
        self.assertTrue(ret['can_activate'])

        job.recipe.private = True
        job.recipe.save()
        # manual recipe. a collaborator can activate
        job.recipe.automatic = models.Recipe.MANUAL
        job.recipe.save()
        session = self.client.session
        ret = Permissions.job_permissions(session, job)
        self.assertFalse(ret['is_owner'])
        self.assertTrue(ret['can_see_results'])
        self.assertTrue(ret['can_admin'])
        self.assertTrue(ret['can_activate'])

        # auto authorized recipe.
        job.recipe.automatic = models.Recipe.AUTO_FOR_AUTHORIZED
        job.recipe.auto_authorized.add(user)
        job.recipe.save()
        ret = Permissions.job_permissions(session, job)
        self.assertFalse(ret['is_owner'])
        self.assertTrue(ret['can_see_results'])
        self.assertTrue(ret['can_admin'])
        self.assertTrue(ret['can_activate'])

        # there was an exception somewhere
        session = self.client.session
        mock_get.side_effect = Exception("Boom!")
        ret = Permissions.job_permissions(session, job)
        self.assertFalse(ret['is_owner'])
        self.assertFalse(ret['can_see_results'])
        self.assertFalse(ret['can_admin'])
        self.assertTrue(ret['can_activate']) # still set because user is in auto_authorized

    @patch.object(OAuth2Session, 'get')
    def test_is_allowed_to_see_clients(self, mock_get):
        user = utils.create_user(name="auth user")
        with self.settings(INSTALLED_GITSERVERS=[utils.github_config(authorized_users=["team"])]):
            # not signed in
            session = self.client.session
            with self.assertNumQueries(1):
                allowed = Permissions.is_allowed_to_see_clients(session)
            self.assertFalse(allowed)

            utils.simulate_login(self.client.session, user)
            session = self.client.session
            # A signed in user, shouldn't match authorized_users
            mock_get.return_value = utils.Response()
            with self.assertNumQueries(3):
                allowed = Permissions.is_allowed_to_see_clients(session)
            self.assertFalse(allowed)
            self.assertEqual(mock_get.call_count, 1)
            session.save()

            # This time it should hit cache
            with self.assertNumQueries(0):
                allowed = Permissions.is_allowed_to_see_clients(session)
            self.assertFalse(allowed)
            self.assertEqual(mock_get.call_count, 1)

            # Clear the cache and try the success route
        with self.settings(INSTALLED_GITSERVERS=[utils.github_config(authorized_users=[user.name])]):
            utils.simulate_login(self.client.session, user)
            session = self.client.session
            mock_get.return_value = utils.Response(status_code=204)

            with self.assertNumQueries(3):
                allowed = Permissions.is_allowed_to_see_clients(session)
            self.assertTrue(allowed)
            self.assertEqual(mock_get.call_count, 1) # team is the same as user name so no call
            session.save()

            # Should hit cache
            with self.assertNumQueries(0):
                allowed = Permissions.is_allowed_to_see_clients(session)
            self.assertTrue(allowed)
            self.assertEqual(mock_get.call_count, 1)

    @patch.object(OAuth2Session, 'get')
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

        session = self.client.session # clears the cache
        # A member
        is_member = Permissions.is_team_member(session, api, user.name, user)
        self.assertTrue(is_member)
        self.assertEqual(mock_get.call_count, 1) # team is the same as user name so no call

        # Should be cached
        is_member = Permissions.is_team_member(session, api, user.name, user)
        self.assertTrue(is_member)
        self.assertEqual(mock_get.call_count, 1)

    @patch.object(OAuth2Session, 'get')
    def test_can_see_results(self, mock_get):
        recipe = utils.create_recipe()
        mock_get.return_value = utils.Response(status_code=404) # not a collaborator

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
        session = self.client.session # so we don't hit the cache
        mock_get.return_value = utils.Response(status_code=204) # a collaborator
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
        session = self.client.session # so we don't hit the cache
        data = {"login": "some team"}
        mock_get.return_value = utils.Response([data])
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

        # A valid member of the team
        session = self.client.session # clear the cache
        data["login"] = "foo"
        mock_get.return_value = utils.Response([data])
        ret = Permissions.can_see_results(session, recipe)
        self.assertTrue(ret)
        self.assertEqual(mock_get.call_count, 1)

        # Again, to test the cache
        mock_get.call_count = 0
        ret = Permissions.can_see_results(session, recipe)
        self.assertTrue(ret)
        self.assertEqual(mock_get.call_count, 0)
