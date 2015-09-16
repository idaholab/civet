from django.test import TestCase, Client
from django.test.client import RequestFactory
from django.core.urlresolvers import reverse
from django.utils import timezone
from mock import patch
import datetime
from ci import models, views
from . import utils
from ci.github import api

class ViewsTestCase(TestCase):
  fixtures = ['base']

  def setUp(self):
    self.client = Client()
    self.factory = RequestFactory()

  def test_main(self):
    """
    testing ci:main
    """
    response = self.client.get(reverse('ci:main'))
    self.assertEqual(response.status_code, 200)
    self.assertIn('GitHub Sign in', response.content)
    self.assertNotIn('Sign out', response.content)

    user = utils.get_test_user()
    utils.simulate_login(self.client.session, user)
    self.assertIn('github_user', self.client.session)
    response = self.client.get(reverse('ci:main'))
    self.assertIn('Sign out', response.content)
    self.assertNotIn('GitHub Sign in', response.content)

  def test_view_pr(self):
    """
    testing ci:view_pr
    """
    response = self.client.get(reverse('ci:view_pr', args=[1000,]))
    self.assertEqual(response.status_code, 404)
    pr = utils.create_pr()
    response = self.client.get(reverse('ci:view_pr', args=[pr.pk]))
    self.assertEqual(response.status_code, 200)

  def test_view_event(self):
    """
    testing ci:view_event
    """
    #invalid event
    response = self.client.get(reverse('ci:view_event', args=[1000,]))
    self.assertEqual(response.status_code, 404)

    #valid event
    ev =  utils.create_event()
    response = self.client.get(reverse('ci:view_event', args=[ev.pk]))
    self.assertEqual(response.status_code, 200)

    #valid event while signed in
    user = utils.get_test_user()
    utils.simulate_login(self.client.session, user)
    response = self.client.get(reverse('ci:view_event', args=[ev.pk]))
    self.assertEqual(response.status_code, 200)

  @patch.object(api.GitHubAPI, 'is_collaborator')
  def test_job_permissions(self, mock_is_collaborator):
    """
    testing views.job_permissions works
    """
    # not the owner and not a collaborator
    mock_is_collaborator.return_value = False
    job = utils.create_job()
    job.recipe.private = False
    job.recipe.save()
    ret = views.job_permissions(self.client.session, job)
    self.assertFalse(ret['is_owner'])
    self.assertTrue(ret['can_see_results']) # not private
    self.assertFalse(ret['can_admin'])
    self.assertFalse(ret['can_activate'])

    job.recipe.private = True
    job.recipe.save()
    ret = views.job_permissions(self.client.session, job)
    self.assertFalse(ret['is_owner'])
    self.assertFalse(ret['can_see_results']) # private
    self.assertFalse(ret['can_admin'])
    self.assertFalse(ret['can_activate'])

    # user is signed in but not a collaborator
    # recipe is still private
    user = utils.get_test_user()
    utils.simulate_login(self.client.session, user)
    ret = views.job_permissions(self.client.session, job)
    self.assertFalse(ret['is_owner'])
    self.assertFalse(ret['can_see_results'])
    self.assertFalse(ret['can_admin'])
    self.assertFalse(ret['can_activate'])

    # user is a collaborator now
    mock_is_collaborator.return_value = True
    ret = views.job_permissions(self.client.session, job)
    self.assertFalse(ret['is_owner'])
    self.assertTrue(ret['can_see_results'])
    self.assertTrue(ret['can_admin'])
    self.assertTrue(ret['can_activate'])

    # manual recipe. a collaborator can activate
    job.recipe.automatic = models.Recipe.MANUAL
    job.recipe.save()
    ret = views.job_permissions(self.client.session, job)
    self.assertFalse(ret['is_owner'])
    self.assertTrue(ret['can_see_results'])
    self.assertTrue(ret['can_admin'])
    self.assertTrue(ret['can_activate'])

    # auto authorized recipe.
    job.recipe.automatic = models.Recipe.AUTO_FOR_AUTHORIZED
    job.recipe.auto_authorized.add(user)
    job.recipe.save()
    ret = views.job_permissions(self.client.session, job)
    self.assertFalse(ret['is_owner'])
    self.assertTrue(ret['can_see_results'])
    self.assertTrue(ret['can_admin'])
    self.assertTrue(ret['can_activate'])

  def test_get_job_info(self):
    c = utils.create_client()
    job = utils.create_job()
    job.client = c
    job.save()

    job_q = models.Job.objects
    job_info = views.get_job_info(job_q, 30)
    self.assertEqual(len(job_info), 1)
    self.assertEqual(job_info[0]['id'], job.pk)
    pr = utils.create_pr()
    job.event.pull_request = pr
    job.event.save()
    job_info = views.get_job_info(job_q, 30)
    self.assertEqual(len(job_info), job.pk)
    self.assertEqual(job_info[0]['id'], job.pk)

  def test_get_repos_status(self):
    repo = utils.create_repo()
    branch = utils.create_branch(repo=repo)
    branch.status = models.JobStatus.SUCCESS
    branch.save()
    pr = utils.create_pr(repo=repo)
    job = utils.create_job()
    job.event.pull_request = pr
    job.event.save()
    data = views.get_repos_status()
    self.assertEqual(len(data), 1)
    dt = timezone.localtime(timezone.now() - datetime.timedelta(seconds=30))
    data = views.get_repos_status(dt)
    self.assertEqual(len(data), 1)

  def test_view_job(self):
    """
    testing ci:view_job
    """
    response = self.client.get(reverse('ci:view_job', args=[1000,]))
    self.assertEqual(response.status_code, 404)
    job = utils.create_job()
    response = self.client.get(reverse('ci:view_job', args=[job.pk]))
    self.assertEqual(response.status_code, 200)

  def test_get_paginated(self):
    recipes = models.Recipe.objects.all()
    request = self.factory.get('/foo?page=1')
    objs = views.get_paginated(request, recipes)
    self.assertEqual(objs.number, 1)

    request = self.factory.get('/foo?page=2')
    objs = views.get_paginated(request, recipes)
    self.assertEqual(objs.number, 1)

    for i in xrange(10):
      utils.create_recipe(name='recipe %s' % i)

    request = self.factory.get('/foo?page=2')
    objs = views.get_paginated(request, recipes, 2)
    self.assertEqual(objs.number, 2)

    request = self.factory.get('/foo?page=20')
    objs = views.get_paginated(request, recipes, 2)
    self.assertEqual(objs.number, 5)

    request = self.factory.get('/foo?page=foo')
    objs = views.get_paginated(request, recipes, 2)
    self.assertEqual(objs.number, 1)

  def test_view_repo(self):
    # invalid repo
    response = self.client.get(reverse('ci:view_repo', args=[1000,]))
    self.assertEqual(response.status_code, 404)

    # valid repo with branches
    repo = utils.create_repo()
    branch = utils.create_branch(repo=repo)
    branch.status = models.JobStatus.FAILED
    branch.save()
    response = self.client.get(reverse('ci:view_repo', args=[repo.pk]))
    self.assertEqual(response.status_code, 200)

  def test_view_client(self):
    response = self.client.get(reverse('ci:view_client', args=[1000,]))
    self.assertEqual(response.status_code, 404)
    client = utils.create_client()
    response = self.client.get(reverse('ci:view_client', args=[client.pk]))
    self.assertEqual(response.status_code, 200)

  def test_view_branch(self):
    response = self.client.get(reverse('ci:view_branch', args=[1000,]))
    self.assertEqual(response.status_code, 404)
    obj = utils.create_branch()
    response = self.client.get(reverse('ci:view_branch', args=[obj.pk]))
    self.assertEqual(response.status_code, 200)

  def test_job_list(self):
    response = self.client.get(reverse('ci:job_list'))
    self.assertEqual(response.status_code, 200)

  def test_pr_list(self):
    response = self.client.get(reverse('ci:pullrequest_list'))
    self.assertEqual(response.status_code, 200)

  def test_branch_list(self):
    response = self.client.get(reverse('ci:branch_list'))
    self.assertEqual(response.status_code, 200)

  def test_client_list(self):
    response = self.client.get(reverse('ci:client_list'))
    self.assertEqual(response.status_code, 200)

  def test_event_list(self):
    response = self.client.get(reverse('ci:event_list'))
    self.assertEqual(response.status_code, 200)

  def test_recipe_events(self):
    response = self.client.get(reverse('ci:recipe_events', args=[1000,]))
    self.assertEqual(response.status_code, 404)

    rc = utils.create_recipe()
    job1 = utils.create_job(recipe=rc)
    job1.status = models.JobStatus.SUCCESS
    job1.save()
    response = self.client.get(reverse('ci:recipe_events', args=[rc.pk]))
    self.assertEqual(response.status_code, 200)

  def permission_response(self, is_owner, can_see_results, can_admin, can_activate):
    return {'is_owner': is_owner,
        'can_see_results': can_see_results,
        'can_admin': can_admin,
        'can_activate': can_activate,
        }

  @patch.object(api.GitHubAPI, 'is_collaborator')
  def test_is_allowed_to_cancel(self, collaborator_mock):
    ev = utils.create_event()
    # not signed in
    self.assertFalse(views.is_allowed_to_cancel(self.client.session, ev))

    user = utils.get_test_user()
    utils.simulate_login(self.client.session, user)
    # not a collaborator
    collaborator_mock.return_value = False
    self.assertFalse(views.is_allowed_to_cancel(self.client.session, ev))

    # valid, a collaborator
    collaborator_mock.return_value = True
    self.assertTrue(views.is_allowed_to_cancel(self.client.session, ev))


  @patch.object(views, 'is_allowed_to_cancel')
  def test_invalidate_event(self, allowed_mock):
    # only post is allowed
    response = self.client.get(reverse('ci:invalidate_event', args=[1000]))
    self.assertEqual(response.status_code, 405) # not allowed

    # invalid event
    response = self.client.post(reverse('ci:invalidate_event', args=[1000]))
    self.assertEqual(response.status_code, 404) # not found

    # can't invalidate
    step_result = utils.create_step_result()
    job = step_result.job
    allowed_mock.return_value = False
    response = self.client.post(reverse('ci:invalidate_event', args=[job.event.pk]))
    self.assertEqual(response.status_code, 403) # forbidden

    # valid
    allowed_mock.return_value = True
    response = self.client.post(reverse('ci:invalidate_event', args=[job.event.pk]))
    self.assertEqual(response.status_code, 302) #redirect
    job = models.Job.objects.get(pk=job.pk)
    self.assertRedirects(response, reverse('ci:view_event', args=[job.event.pk]))
    self.assertEqual(job.step_results.count(), 0)
    self.assertFalse(job.complete)
    self.assertTrue(job.active)
    self.assertEqual(job.seconds.seconds, 0)
    self.assertEqual(job.status, models.JobStatus.NOT_STARTED)
    self.assertFalse(job.event.complete)
    self.assertEqual(job.event.status, models.JobStatus.NOT_STARTED)

  @patch.object(views, 'is_allowed_to_cancel')
  def test_cancel_event(self, allowed_mock):
    # only post is allowed
    response = self.client.get(reverse('ci:cancel_event', args=[1000]))
    self.assertEqual(response.status_code, 405) # not allowed

    # invalid event
    response = self.client.post(reverse('ci:cancel_event', args=[1000]))
    self.assertEqual(response.status_code, 404) # not found

    # can't cancel
    step_result = utils.create_step_result()
    job = step_result.job
    allowed_mock.return_value = False
    response = self.client.post(reverse('ci:cancel_event', args=[job.event.pk]))
    self.assertEqual(response.status_code, 403) # forbidden

    # valid
    allowed_mock.return_value = True
    response = self.client.post(reverse('ci:cancel_event', args=[job.event.pk]))
    self.assertEqual(response.status_code, 302) #redirect
    job = models.Job.objects.get(pk=job.pk)
    self.assertRedirects(response, reverse('ci:view_event', args=[job.event.pk]))
    self.assertEqual(job.status, models.JobStatus.CANCELED)
    self.assertEqual(job.event.status, models.JobStatus.CANCELED)

  @patch.object(views, 'is_allowed_to_cancel')
  def test_cancel_job(self, allowed_mock):
    # only post is allowed
    response = self.client.get(reverse('ci:cancel_job', args=[1000]))
    self.assertEqual(response.status_code, 405) # not allowed

    # invalid job
    response = self.client.post(reverse('ci:cancel_job', args=[1000]))
    self.assertEqual(response.status_code, 404) # not found

    # can't cancel
    step_result = utils.create_step_result()
    job = step_result.job
    allowed_mock.return_value = False
    response = self.client.post(reverse('ci:cancel_job', args=[job.pk]))
    self.assertEqual(response.status_code, 403) # forbidden

    # valid
    allowed_mock.return_value = True
    response = self.client.post(reverse('ci:cancel_job', args=[job.pk]))
    self.assertEqual(response.status_code, 302) #redirect
    job = models.Job.objects.get(pk=job.pk)
    self.assertRedirects(response, reverse('ci:view_job', args=[job.pk]))
    self.assertEqual(job.status, models.JobStatus.CANCELED)

  @patch.object(views, 'is_allowed_to_cancel')
  def test_invalidate(self, allowed_mock):
    # only post is allowed
    response = self.client.get(reverse('ci:invalidate', args=[1000]))
    self.assertEqual(response.status_code, 405) # not allowed

    # invalid job
    response = self.client.post(reverse('ci:invalidate', args=[1000]))
    self.assertEqual(response.status_code, 404) # not found

    # can't invalidate
    step_result = utils.create_step_result()
    job = step_result.job
    allowed_mock.return_value = False
    response = self.client.post(reverse('ci:invalidate', args=[job.pk]))
    self.assertEqual(response.status_code, 403) # forbidden

    # valid
    allowed_mock.return_value = True
    response = self.client.post(reverse('ci:invalidate', args=[job.pk]))
    self.assertEqual(response.status_code, 302) #redirect
    job = models.Job.objects.get(pk=job.pk)
    self.assertRedirects(response, reverse('ci:view_job', args=[job.pk]))
    self.assertEqual(job.step_results.count(), 0)
    self.assertFalse(job.complete)
    self.assertTrue(job.active)
    self.assertEqual(job.seconds.seconds, 0)
    self.assertEqual(job.status, models.JobStatus.NOT_STARTED)

  def test_view_profile(self):
    # invalid git server
    response = self.client.get(reverse('ci:view_profile', args=[1000]))
    self.assertEqual(response.status_code, 404)

    # not signed in should redirect to sign in
    server = utils.create_git_server()
    response = self.client.get(reverse('ci:view_profile', args=[server.host_type]))
    self.assertEqual(response.status_code, 302) # redirect

    # signed in
    user = utils.get_test_user()
    utils.simulate_login(self.client.session, user)
    response = self.client.get(reverse('ci:view_profile', args=[user.server.host_type]))
    self.assertEqual(response.status_code, 200)

  @patch.object(api.GitHubAPI, 'is_collaborator')
  def test_activate_job(self, api_mock):
    # only posts are allowed
    response = self.client.get(reverse('ci:activate_job', args=[1000]))
    self.assertEqual(response.status_code, 405)

    response = self.client.post(reverse('ci:activate_job', args=[1000]))
    self.assertEqual(response.status_code, 404)

    job = utils.create_job()
    job.active = False
    job.save()
    response = self.client.post(reverse('ci:activate_job', args=[job.pk]))
    # not signed in
    self.assertEqual(response.status_code, 403)

    user = utils.get_test_user()
    utils.simulate_login(self.client.session, user)
    api_mock.return_value = False
    response = self.client.post(reverse('ci:activate_job', args=[job.pk]))
    # not a collaborator
    job = models.Job.objects.get(pk=job.pk)
    self.assertEqual(response.status_code, 403)
    self.assertFalse(job.active)

    api_mock.return_value = True
    response = self.client.post(reverse('ci:activate_job', args=[job.pk]))
    # not a collaborator
    job = models.Job.objects.get(pk=job.pk)
    self.assertEqual(response.status_code, 302) # redirect
    self.assertTrue(job.active)

  def test_start_session(self):
    response = self.client.get(reverse('ci:start_session', args=[1000]))
    self.assertEqual(response.status_code, 404)

    user = utils.get_test_user()
    owner = utils.get_owner()
    response = self.client.get(reverse('ci:start_session', args=[owner.pk]))
    # owner doesn't have a token
    self.assertEqual(response.status_code, 404)

    response = self.client.get(reverse('ci:start_session', args=[user.pk]))
    self.assertEqual(response.status_code, 302)
    self.assertIn('github_user', self.client.session)
    self.assertIn('github_token', self.client.session)

  def test_start_session_by_name(self):
    # invalid name
    response = self.client.get(reverse('ci:start_session_by_name', args=['nobody']))
    self.assertEqual(response.status_code, 404)

    user = utils.get_test_user()
    owner = utils.get_owner()
    # owner doesn't have a token
    response = self.client.get(reverse('ci:start_session_by_name', args=[owner.name]))
    self.assertEqual(response.status_code, 404)

    # valid, user has a token
    response = self.client.get(reverse('ci:start_session_by_name', args=[user.name]))
    self.assertEqual(response.status_code, 302)
    self.assertIn('github_user', self.client.session)
    self.assertIn('github_token', self.client.session)

  @patch.object(models.GitUser, 'start_session')
  @patch.object(api.GitHubAPI, 'last_sha')
  def test_manual(self, last_sha_mock, user_mock):
    last_sha_mock.return_value = '1234'
    response = self.client.get(reverse('ci:manual_branch', args=[1000,1000]))
    # only post allowed
    self.assertEqual(response.status_code, 405)

    test_user = utils.get_test_user()
    owner = utils.get_owner()
    jobs_before = models.Job.objects.filter(ready=True).count()
    events_before = models.Event.objects.count()

    repo = utils.create_repo(name='repo02', user=owner)
    branch = utils.create_branch(name='devel', repo=repo)

    user_mock.return_value = test_user.server.auth().start_session_for_user(test_user)
    response = self.client.post(reverse('ci:manual_branch', args=[test_user.build_key, branch.pk]))
    self.assertEqual(response.status_code, 200)
    self.assertIn('Success', response.content)

    # no recipes are there so no events/jobs should be created
    jobs_after = models.Job.objects.filter(ready=True).count()
    events_after = models.Event.objects.count()
    self.assertEqual(events_after, events_before)
    self.assertEqual(jobs_after, jobs_before)

    utils.create_recipe(user=test_user, repo=repo, branch=branch, cause=models.Recipe.CAUSE_MANUAL) # just create it so a job will get created

    response = self.client.post(reverse('ci:manual_branch', args=[test_user.build_key, branch.pk]))
    self.assertEqual(response.status_code, 200)
    self.assertIn('Success', response.content)

    jobs_after = models.Job.objects.filter(ready=True).count()
    events_after = models.Event.objects.count()
    self.assertGreater(events_after, events_before)
    self.assertGreater(jobs_after, jobs_before)

    response = self.client.post(
        reverse('ci:manual_branch', args=[test_user.build_key, branch.pk]),
        {'next': reverse('ci:main'),
        })
    self.assertEqual(response.status_code, 302) # redirect

    user_mock.side_effect = Exception
    response = self.client.post(reverse('ci:manual_branch', args=[test_user.build_key, branch.pk]))
    self.assertIn('Error', response.content)
