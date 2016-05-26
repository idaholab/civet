from django.test import TestCase, Client
from django.conf import settings
from mock import patch
from ci import models, Permissions
from . import utils
from ci.github import api

class PermissionsTestCase(TestCase):
  fixtures = ['base']

  def setUp(self):
    self.client = Client()
    settings.INSTALLED_GITSERVERS = [settings.GITSERVER_GITHUB]
    self.orig_timeout = settings.COLLABORATOR_CACHE_TIMEOUT

  def tearDown(self):
    settings.COLLABORATOR_CACHE_TIMEOUT = self.orig_timeout

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
  def test_job_permissions(self, mock_is_collaborator):
    """
    testing Permissions.job_permissions works
    Note that with the way we are using sessions here we
    will never hit the cache since these sessions require
    you to make a copy and then call save
    """
    # not the owner and not a collaborator
    mock_is_collaborator.return_value = False
    job = utils.create_job()
    job.recipe.private = False
    job.recipe.save()
    ret = Permissions.job_permissions(self.client.session, job)
    self.assertFalse(ret['is_owner'])
    self.assertTrue(ret['can_see_results']) # not private
    self.assertFalse(ret['can_admin'])
    self.assertFalse(ret['can_activate'])

    job.recipe.private = True
    job.recipe.save()
    ret = Permissions.job_permissions(self.client.session, job)
    self.assertFalse(ret['is_owner'])
    self.assertFalse(ret['can_see_results']) # private
    self.assertFalse(ret['can_admin'])
    self.assertFalse(ret['can_activate'])

    # user is signed in but not a collaborator
    # recipe is still private
    user = utils.get_test_user()
    utils.simulate_login(self.client.session, user)
    ret = Permissions.job_permissions(self.client.session, job)
    self.assertFalse(ret['is_owner'])
    self.assertFalse(ret['can_see_results'])
    self.assertFalse(ret['can_admin'])
    self.assertFalse(ret['can_activate'])

    # user is a collaborator now
    mock_is_collaborator.return_value = True
    ret = Permissions.job_permissions(self.client.session, job)
    self.assertFalse(ret['is_owner'])
    self.assertTrue(ret['can_see_results'])
    self.assertTrue(ret['can_admin'])
    self.assertTrue(ret['can_activate'])

    # manual recipe. a collaborator can activate
    job.recipe.automatic = models.Recipe.MANUAL
    job.recipe.save()
    ret = Permissions.job_permissions(self.client.session, job)
    self.assertFalse(ret['is_owner'])
    self.assertTrue(ret['can_see_results'])
    self.assertTrue(ret['can_admin'])
    self.assertTrue(ret['can_activate'])

    # auto authorized recipe.
    job.recipe.automatic = models.Recipe.AUTO_FOR_AUTHORIZED
    job.recipe.auto_authorized.add(user)
    job.recipe.save()
    ret = Permissions.job_permissions(self.client.session, job)
    self.assertFalse(ret['is_owner'])
    self.assertTrue(ret['can_see_results'])
    self.assertTrue(ret['can_admin'])
    self.assertTrue(ret['can_activate'])

    # there was an exception somewhere
    mock_is_collaborator.side_effect = Exception
    ret = Permissions.job_permissions(self.client.session, job)
    self.assertFalse(ret['is_owner'])
    self.assertFalse(ret['can_see_results'])
    self.assertFalse(ret['can_admin'])
    self.assertTrue(ret['can_activate'])

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


  @patch.object(api.GitHubAPI, 'is_collaborator')
  def test_is_allowed_to_see_clients(self, collaborator_mock):
    user = utils.create_user(name="auth user")
    other_user = utils.create_user(name="other")
    utils.create_repo(user=user)
    settings.AUTHORIZED_OWNERS = [other_user]
    # not signed in
    session = self.client.session
    with self.assertNumQueries(1):
      allowed = Permissions.is_allowed_to_see_clients(session)
    self.assertFalse(allowed)

    utils.simulate_login(self.client.session, user)
    session = self.client.session
    # Now try again. The owner doesn't have any repos though
    collaborator_mock.return_value = False
    allowed = Permissions.is_allowed_to_see_clients(session)
    self.assertFalse(allowed)
    self.assertEqual(collaborator_mock.call_count, 0)
    session.save()

    # Now the owner has a repo and the user is allowed
    # But we hit the cache
    collaborator_mock.return_value = True
    utils.create_repo(user=other_user)
    with self.assertNumQueries(0):
      allowed = Permissions.is_allowed_to_see_clients(session)
    self.assertFalse(allowed)
    self.assertEqual(collaborator_mock.call_count, 0)

    # same setup without the cache
    # Now try again. Not authorized
    session.clear()
    utils.simulate_login(session, user)
    allowed = Permissions.is_allowed_to_see_clients(session)
    self.assertTrue(allowed)
    self.assertEqual(collaborator_mock.call_count, 1)
    session.save()

    # Now try again.
    collaborator_mock.call_count = 0
    with self.assertNumQueries(0):
      allowed = Permissions.is_allowed_to_see_clients(session)
    self.assertTrue(allowed)
    self.assertEqual(collaborator_mock.call_count, 0)
    session.save()

    # cache is cleared
    settings.COLLABORATOR_CACHE_TIMEOUT = 0
    session.clear()
    utils.simulate_login(session, user)
    allowed = Permissions.is_allowed_to_see_clients(session)
    self.assertTrue(allowed)
    self.assertEqual(collaborator_mock.call_count, 1)
    session.save()

    # not using the cache
    collaborator_mock.call_count = 0
    allowed = Permissions.is_allowed_to_see_clients(session)
    self.assertTrue(allowed)
    self.assertEqual(collaborator_mock.call_count, 1)
    session.save()
