
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

from django.conf import settings
from mock import patch
from ci import models, Permissions
from . import utils
from ci.github import api
from ci.tests import DBTester

class Tests(DBTester.DBTester):
    def setUp(self):
        super(Tests, self).setUp()
        self.orig_servers = settings.INSTALLED_GITSERVERS
        settings.INSTALLED_GITSERVERS = [settings.GITSERVER_GITHUB]
        settings.COLLABORATOR_CACHE_TIMEOUT = 10

    def tearDown(self):
        super(Tests, self).tearDown()
        settings.INSTALLED_GITSERVERS = self.orig_servers

    @patch.object(api.GitHubAPI, 'is_collaborator')
    def test_is_collaborator(self, collaborator_mock):
        build_user = utils.create_user_with_token(name="build user")
        repo = utils.create_repo()
        auth = build_user.server.auth()
        user = utils.create_user(name="auth user")
        # not signed in
        session = self.client.session
        with self.assertNumQueries(0):
            allowed, signed_in_user = Permissions.is_collaborator(auth, session, build_user, repo)
        self.assertFalse(allowed)
        self.assertEqual(signed_in_user, None)

        utils.simulate_login(self.client.session, user)
        session = self.client.session
        # not a collaborator
        collaborator_mock.return_value = False
        allowed, signed_in_user = Permissions.is_collaborator(auth, session, build_user, repo)
        self.assertFalse(allowed)
        self.assertEqual(signed_in_user, user)
        self.assertEqual(collaborator_mock.call_count, 1)
        session.save() # make sure the cache is saved

        # Now try again. The only query should be to get the signed in user
        collaborator_mock.call_count = 0
        with self.assertNumQueries(1):
            allowed, signed_in_user = Permissions.is_collaborator(auth, session, build_user, repo)
        self.assertFalse(allowed)
        self.assertEqual(signed_in_user, user)
        self.assertEqual(collaborator_mock.call_count, 0)
        session.save()

        # Now try again. We pass in the user so there shouldn't be any queries
        with self.assertNumQueries(0):
            allowed, signed_in_user = Permissions.is_collaborator(auth, session, build_user, repo, user=user)
        self.assertFalse(allowed)
        self.assertEqual(signed_in_user, user)
        self.assertEqual(collaborator_mock.call_count, 0)
        session.save()

        # Just to make sure, it would be allowed but we still read from the cache
        collaborator_mock.return_value = True
        with self.assertNumQueries(0):
            allowed, signed_in_user = Permissions.is_collaborator(auth, session, build_user, repo, user=user)
        self.assertFalse(allowed)
        self.assertEqual(signed_in_user, user)
        self.assertEqual(collaborator_mock.call_count, 0)
        session.save()

        # now start over with no timeout
        settings.COLLABORATOR_CACHE_TIMEOUT = 0
        session.clear()
        utils.simulate_login(session, user)
        collaborator_mock.call_count = 0
        collaborator_mock.return_value = False

        with self.assertNumQueries(0):
            allowed, signed_in_user = Permissions.is_collaborator(auth, session, build_user, repo, user=user)
        self.assertFalse(allowed)
        self.assertEqual(signed_in_user, user)
        self.assertEqual(collaborator_mock.call_count, 1)
        session.save()

        # and again
        collaborator_mock.call_count = 0
        with self.assertNumQueries(0):
            allowed, signed_in_user = Permissions.is_collaborator(auth, session, build_user, repo, user=user)
        self.assertFalse(allowed)
        self.assertEqual(signed_in_user, user)
        self.assertEqual(collaborator_mock.call_count, 1)
        session.save()

        collaborator_mock.return_value = True
        # Should be good
        collaborator_mock.call_count = 0
        with self.assertNumQueries(0):
            allowed, signed_in_user = Permissions.is_collaborator(auth, session, build_user, repo, user=user)
        self.assertTrue(allowed)
        self.assertEqual(signed_in_user, user)
        self.assertEqual(collaborator_mock.call_count, 1)
        session.save()

        collaborator_mock.side_effect = Exception("Boom!")
        # On error, no collaborator, no user
        collaborator_mock.call_count = 0
        with self.assertNumQueries(0):
            allowed, signed_in_user = Permissions.is_collaborator(auth, session, build_user, repo, user=user)
        self.assertFalse(allowed)
        self.assertEqual(signed_in_user, None)
        self.assertEqual(collaborator_mock.call_count, 1)

    @patch.object(api.GitHubAPI, 'is_collaborator')
    @patch.object(api.GitHubAPI, 'is_member')
    def test_job_permissions(self, mock_is_member, mock_is_collaborator):
        """
        testing Permissions.job_permissions works
        """
        # not the owner and not a collaborator
        mock_is_collaborator.return_value = False
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
        session = self.client.session
        mock_is_collaborator.return_value = True
        ret = Permissions.job_permissions(session, job)
        self.assertFalse(ret['is_owner'])
        self.assertTrue(ret['can_see_results'])
        self.assertTrue(ret['can_admin'])
        self.assertTrue(ret['can_activate'])

        # user is a collaborator and the recipe is not private
        job.recipe.private = False
        job.recipe.save()
        session = self.client.session
        mock_is_collaborator.return_value = True
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
        mock_is_collaborator.side_effect = Exception
        ret = Permissions.job_permissions(session, job)
        self.assertFalse(ret['is_owner'])
        self.assertFalse(ret['can_see_results'])
        self.assertFalse(ret['can_admin'])
        self.assertTrue(ret['can_activate']) # still set because user is in auto_authorized

    @patch.object(api.GitHubAPI, 'is_collaborator')
    def test_is_allowed_to_cancel(self, collaborator_mock):
        """
        Note that with the way we are using sessions here we
        will never hit the cache since these sessions require
        you to make a copy and then call save
        """
        ev = utils.create_event()
        # not signed in
        allowed, signed_in_user = Permissions.is_allowed_to_cancel(self.client.session, ev)
        self.assertFalse(allowed)
        self.assertEqual(signed_in_user, None)

        user = utils.get_test_user()
        utils.simulate_login(self.client.session, user)
        # not a collaborator
        collaborator_mock.return_value = False
        allowed, signed_in_user = Permissions.is_allowed_to_cancel(self.client.session, ev)
        self.assertFalse(allowed)
        self.assertEqual(signed_in_user, user)

        # valid, a collaborator
        collaborator_mock.return_value = True
        allowed, signed_in_user = Permissions.is_allowed_to_cancel(self.client.session, ev)
        self.assertTrue(allowed)
        self.assertEqual(signed_in_user, user)

        # there was an exception somewhere
        collaborator_mock.side_effect = Exception
        allowed, signed_in_user = Permissions.is_allowed_to_cancel(self.client.session, ev)
        self.assertFalse(allowed)
        self.assertEqual(signed_in_user, None)

    @patch.object(api.GitHubAPI, 'is_member')
    def test_is_allowed_to_see_clients(self, member_mock):
        user = utils.create_user(name="auth user")
        settings.AUTHORIZED_USERS = ["team"]
        # not signed in
        session = self.client.session
        with self.assertNumQueries(1):
            allowed = Permissions.is_allowed_to_see_clients(session)
        self.assertFalse(allowed)

        utils.simulate_login(self.client.session, user)
        session = self.client.session
        # A signed in user, shouldn't match AUTHORIZED_USERS
        member_mock.return_value = False
        with self.assertNumQueries(3):
            allowed = Permissions.is_allowed_to_see_clients(session)
        self.assertFalse(allowed)
        self.assertEqual(member_mock.call_count, 1)
        session.save()

        # This time it should hit cache
        with self.assertNumQueries(0):
            allowed = Permissions.is_allowed_to_see_clients(session)
        self.assertFalse(allowed)
        self.assertEqual(member_mock.call_count, 1)

        # Clear the cache and try the success route
        utils.simulate_login(self.client.session, user)
        session = self.client.session
        member_mock.return_value = True

        with self.assertNumQueries(3):
            allowed = Permissions.is_allowed_to_see_clients(session)
        self.assertTrue(allowed)
        self.assertEqual(member_mock.call_count, 2)
        session.save()

        # Should hit cache
        with self.assertNumQueries(0):
            allowed = Permissions.is_allowed_to_see_clients(session)
        self.assertTrue(allowed)
        self.assertEqual(member_mock.call_count, 2)

    @patch.object(api.GitHubAPI, 'is_member')
    def test_is_team_member(self, member_mock):
        user = utils.create_user(name="auth user")
        auth = user.server.auth()
        api = user.server.api()
        member_mock.return_value = False
        session = self.client.session
        # Not a member
        is_member = Permissions.is_team_member(session, api, auth, "team", user)
        self.assertFalse(is_member)
        self.assertEqual(member_mock.call_count, 1)

        # Should be cached
        is_member = Permissions.is_team_member(session, api, auth, "team", user)
        self.assertFalse(is_member)
        self.assertEqual(member_mock.call_count, 1)

        session = self.client.session # clears the cache
        member_mock.return_value = True
        # A member
        is_member = Permissions.is_team_member(session, api, auth, "team", user)
        self.assertTrue(is_member)
        self.assertEqual(member_mock.call_count, 2)

        # Should be cached
        is_member = Permissions.is_team_member(session, api, auth, "team", user)
        self.assertTrue(is_member)
        self.assertEqual(member_mock.call_count, 2)

    @patch.object(api.GitHubAPI, 'is_member')
    @patch.object(api.GitHubAPI, 'is_collaborator')
    def test_can_see_results(self, collab_mock, member_mock):
        recipe = utils.create_recipe()
        member_mock.return_value = False
        collab_mock.return_value = False

        session = self.client.session

        # Recipe isn't private, everybody can see it, even
        # when not signed in
        recipe.private = False
        recipe.save()
        ret = Permissions.can_see_results(session, recipe)
        self.assertTrue(ret)
        self.assertEqual(collab_mock.call_count, 0)
        self.assertEqual(member_mock.call_count, 0)

        # Recipe is private, not signed in users can't see it
        recipe.private = True
        recipe.save()
        ret = Permissions.can_see_results(session, recipe)
        self.assertFalse(ret)
        self.assertEqual(collab_mock.call_count, 0)
        self.assertEqual(member_mock.call_count, 0)

        # The build_user should always be able to see results
        utils.simulate_login(self.client.session, recipe.build_user)
        session = self.client.session
        ret = Permissions.can_see_results(session, recipe)
        self.assertTrue(ret)
        self.assertEqual(collab_mock.call_count, 0)
        self.assertEqual(member_mock.call_count, 0)

        # A normal user that isn't a collaborator
        user = utils.create_user(name="some user")
        utils.simulate_login(self.client.session, user)
        session = self.client.session
        ret = Permissions.can_see_results(session, recipe)
        self.assertFalse(ret)
        self.assertEqual(collab_mock.call_count, 1)
        self.assertEqual(member_mock.call_count, 0)

        # A normal user that is a collaborator
        session = self.client.session # so we don't hit the cache
        collab_mock.return_value = True
        ret = Permissions.can_see_results(session, recipe)
        self.assertTrue(ret)
        self.assertEqual(collab_mock.call_count, 2)
        self.assertEqual(member_mock.call_count, 0)

        # Again, to test the cache
        ret = Permissions.can_see_results(session, recipe)
        self.assertTrue(ret)
        self.assertEqual(collab_mock.call_count, 2)
        self.assertEqual(member_mock.call_count, 0)

        # Now try with teams
        session = self.client.session # so we don't hit the cache
        collab_mock.return_value = False
        models.RecipeViewableByTeam.objects.create(team="foo", recipe=recipe)

        # Not a member of the team
        ret = Permissions.can_see_results(session, recipe)
        self.assertFalse(ret)
        self.assertEqual(collab_mock.call_count, 2)
        self.assertEqual(member_mock.call_count, 1)

        # Again, to test the cache
        ret = Permissions.can_see_results(session, recipe)
        self.assertFalse(ret)
        self.assertEqual(collab_mock.call_count, 2)
        self.assertEqual(member_mock.call_count, 1)

        # A valid member of the team
        session = self.client.session # clear the cache
        member_mock.return_value = True
        ret = Permissions.can_see_results(session, recipe)
        self.assertTrue(ret)
        self.assertEqual(collab_mock.call_count, 2)
        self.assertEqual(member_mock.call_count, 2)

        # Again, to test the cache
        ret = Permissions.can_see_results(session, recipe)
        self.assertTrue(ret)
        self.assertEqual(collab_mock.call_count, 2)
        self.assertEqual(member_mock.call_count, 2)
