from django.test import Client
from django.test.client import RequestFactory
from django.core.urlresolvers import reverse
from django.utils import timezone
from django.conf import settings
from mock import patch
import datetime
from ci import models, views, Permissions
from . import utils
from ci.github import api
from ci.recipe.tests import utils as recipe_test_utils

class ViewsTests(recipe_test_utils.RecipeTestCase):
  fixtures = ['base']

  def setUp(self):
    super(ViewsTests, self).setUp()
    self.client = Client()
    self.factory = RequestFactory()
    self.old_servers = settings.INSTALLED_GITSERVERS
    settings.INSTALLED_GITSERVERS = [settings.GITSERVER_GITHUB]
    self.set_counts()
    self.create_default_recipes()
    self.compare_counts(recipes=6, deps=2, sha_changed=True, current=6, num_push_recipes=2, num_pr_recipes=2, num_manual_recipes=1, num_pr_alt_recipes=1, users=2, repos=1, branches=1)

  def tearDown(self):
    super(ViewsTests, self).tearDown()
    settings.INSTALLED_GITSERVERS = self.old_servers

  def test_main(self):
    """
    testing ci:main
    """
    response = self.client.get(reverse('ci:main'))
    self.assertEqual(response.status_code, 200)
    self.assertIn('Sign in', response.content)
    self.assertNotIn('Sign out', response.content)

    user = utils.get_test_user()
    utils.simulate_login(self.client.session, user)
    self.assertIn('github_user', self.client.session)
    response = self.client.get(reverse('ci:main'))
    self.assertIn('Sign out', response.content)
    self.assertNotIn('Sign in', response.content)

  def test_view_pr(self):
    """
    testing ci:view_pr
    """
    response = self.client.get(reverse('ci:view_pr', args=[1000,]))
    self.assertEqual(response.status_code, 404)
    pr = utils.create_pr()
    ev = utils.create_event()
    ev.pull_request = pr
    ev.save()
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
    self.assertEqual(len(job_info), 1)
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
    self.assertEqual(models.Recipe.objects.count(), 6)
    # there are 6 recipes, so only 1 page
    # objs.number is the current page number
    request = self.factory.get('/foo?page=1')
    objs = views.get_paginated(request, recipes)
    self.assertEqual(objs.number, 1)
    self.assertEqual(objs.paginator.num_pages, 1)
    self.assertEqual(objs.paginator.count, 6)

    # Invalid page, so just returns the end page
    request = self.factory.get('/foo?page=2')
    objs = views.get_paginated(request, recipes)
    self.assertEqual(objs.number, 1)
    self.assertEqual(objs.paginator.num_pages, 1)
    self.assertEqual(objs.paginator.count, 6)

    for i in xrange(10):
      utils.create_recipe(name='recipe %s' % i)

    # now there are 16 recipes, so page=2 should be
    # valid
    request = self.factory.get('/foo?page=2')
    objs = views.get_paginated(request, recipes, 2)
    self.assertEqual(objs.number, 2)
    self.assertEqual(objs.paginator.num_pages, 8)
    self.assertEqual(objs.paginator.count, 16)

    # page=20 doesn't exist so it should return
    # the last page
    request = self.factory.get('/foo?page=20')
    objs = views.get_paginated(request, recipes, 2)
    self.assertEqual(objs.number, 8)
    self.assertEqual(objs.paginator.num_pages, 8)
    self.assertEqual(objs.paginator.count, 16)

    # Completely invalid page number so returns
    # the first page
    request = self.factory.get('/foo?page=foo')
    objs = views.get_paginated(request, recipes, 2)
    self.assertEqual(objs.number, 1)
    self.assertEqual(objs.paginator.num_pages, 8)
    self.assertEqual(objs.paginator.count, 16)

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

  @patch.object(api.GitHubAPI, 'is_collaborator')
  def test_view_client(self, mock_collab):
    user = utils.get_test_user()
    settings.AUTHORIZED_OWNERS = [user.name,]
    response = self.client.get(reverse('ci:view_client', args=[1000,]))
    self.assertEqual(response.status_code, 404)
    client = utils.create_client()

    # not logged in
    mock_collab.return_value = False
    response = self.client.get(reverse('ci:view_client', args=[client.pk]))
    self.assertEqual(response.status_code, 200)
    self.assertEqual(mock_collab.call_count, 0)

    # logged in and a collaborator
    mock_collab.return_value = True
    utils.simulate_login(self.client.session, user)
    response = self.client.get(reverse('ci:view_client', args=[client.pk]))
    self.assertEqual(response.status_code, 200)
    self.assertEqual(mock_collab.call_count, 1)

  def test_view_branch(self):
    response = self.client.get(reverse('ci:view_branch', args=[1000,]))
    self.assertEqual(response.status_code, 404)
    obj = utils.create_branch()
    response = self.client.get(reverse('ci:view_branch', args=[obj.pk]))
    self.assertEqual(response.status_code, 200)

  def test_pr_list(self):
    response = self.client.get(reverse('ci:pullrequest_list'))
    self.assertEqual(response.status_code, 200)

  def test_branch_list(self):
    response = self.client.get(reverse('ci:branch_list'))
    self.assertEqual(response.status_code, 200)

  @patch.object(api.GitHubAPI, 'is_collaborator')
  def test_client_list(self, mock_collab):
    user = utils.get_test_user()
    settings.AUTHORIZED_OWNERS = [user.name,]

    # not logged in
    response = self.client.get(reverse('ci:client_list'))
    self.assertEqual(response.status_code, 200)

    # not a collaborator
    user = utils.get_test_user()
    utils.simulate_login(self.client.session, user)
    mock_collab.return_value = False
    response = self.client.get(reverse('ci:client_list'))
    self.assertEqual(response.status_code, 200)

    mock_collab.return_value = True
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

  @patch.object(Permissions, 'is_allowed_to_cancel')
  def test_invalidate_event(self, allowed_mock):
    # only post is allowed
    url = reverse('ci:invalidate_event', args=[1000])
    response = self.client.get(url)
    self.assertEqual(response.status_code, 405) # not allowed

    # invalid event
    response = self.client.post(url)
    self.assertEqual(response.status_code, 404) # not found

    # can't invalidate
    step_result = utils.create_step_result()
    job = step_result.job
    allowed_mock.return_value = (False, None)
    url = reverse('ci:invalidate_event', args=[job.event.pk])
    response = self.client.post(url)
    self.assertEqual(response.status_code, 403) # forbidden

    client = utils.create_client()
    job.client = client
    job.save()
    # valid
    post_data = {'same_client': None}
    allowed_mock.return_value = (True, job.event.build_user)
    response = self.client.post(url, data=post_data)
    self.assertEqual(response.status_code, 302) #redirect
    job = models.Job.objects.get(pk=job.pk)
    redir_url = reverse('ci:view_event', args=[job.event.pk])
    self.assertRedirects(response, redir_url)
    self.assertEqual(job.step_results.count(), 0)
    self.assertFalse(job.complete)
    self.assertTrue(job.active)
    self.assertTrue(job.invalidated)
    self.assertFalse(job.same_client)
    self.assertEqual(job.client, None)
    self.assertEqual(job.seconds.seconds, 0)
    self.assertEqual(job.status, models.JobStatus.NOT_STARTED)
    self.assertFalse(job.event.complete)
    self.assertEqual(job.event.status, models.JobStatus.NOT_STARTED)

    # valid
    job.client = client
    job.save()
    utils.create_step_result(job=job)
    post_data = {'same_client': 'on'}
    response = self.client.post(url, data=post_data)
    self.assertEqual(response.status_code, 302) #redirect
    job = models.Job.objects.get(pk=job.pk)
    self.assertRedirects(response, redir_url)
    self.assertEqual(job.step_results.count(), 0)
    self.assertFalse(job.complete)
    self.assertTrue(job.active)
    self.assertTrue(job.invalidated)
    self.assertTrue(job.same_client)
    self.assertEqual(job.client, client)
    self.assertEqual(job.seconds.seconds, 0)
    self.assertEqual(job.status, models.JobStatus.NOT_STARTED)
    self.assertFalse(job.event.complete)
    self.assertEqual(job.event.status, models.JobStatus.NOT_STARTED)

  @patch.object(Permissions, 'is_allowed_to_cancel')
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
    allowed_mock.return_value = (False, None)
    response = self.client.post(reverse('ci:cancel_event', args=[job.event.pk]))
    self.assertEqual(response.status_code, 403) # forbidden

    # valid
    allowed_mock.return_value = (True, job.event.build_user)
    response = self.client.post(reverse('ci:cancel_event', args=[job.event.pk]))
    self.assertEqual(response.status_code, 302) #redirect
    job = models.Job.objects.get(pk=job.pk)
    self.assertRedirects(response, reverse('ci:view_event', args=[job.event.pk]))
    self.assertEqual(job.status, models.JobStatus.CANCELED)
    self.assertEqual(job.event.status, models.JobStatus.CANCELED)

  @patch.object(Permissions, 'is_allowed_to_cancel')
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
    allowed_mock.return_value = (False, None)
    response = self.client.post(reverse('ci:cancel_job', args=[job.pk]))
    self.assertEqual(response.status_code, 403) # forbidden

    # valid
    user = utils.get_test_user()
    allowed_mock.return_value = (True, user)
    response = self.client.post(reverse('ci:cancel_job', args=[job.pk]))
    self.assertEqual(response.status_code, 302) #redirect
    job = models.Job.objects.get(pk=job.pk)
    self.assertRedirects(response, reverse('ci:view_job', args=[job.pk]))
    self.assertEqual(job.status, models.JobStatus.CANCELED)

  @patch.object(Permissions, 'is_allowed_to_cancel')
  def test_invalidate(self, allowed_mock):
    # only post is allowed
    url = reverse('ci:invalidate', args=[1000])
    response = self.client.get(url)
    self.assertEqual(response.status_code, 405) # not allowed

    # invalid job
    response = self.client.post(url)
    self.assertEqual(response.status_code, 404) # not found

    # can't invalidate
    step_result = utils.create_step_result()
    job = step_result.job
    allowed_mock.return_value = (False, None)
    url = reverse('ci:invalidate', args=[job.pk])
    response = self.client.post(url)
    self.assertEqual(response.status_code, 403) # forbidden

    # valid
    client = utils.create_client()
    job.client = client
    job.save()
    post_data = {'same_client':None}
    allowed_mock.return_value = (True, job.event.build_user)
    response = self.client.post(url, data=post_data)
    self.assertEqual(response.status_code, 302) #redirect
    job.refresh_from_db()
    redir_url = reverse('ci:view_job', args=[job.pk])
    self.assertRedirects(response, redir_url)
    self.assertEqual(job.step_results.count(), 0)
    self.assertFalse(job.complete)
    self.assertTrue(job.active)
    self.assertTrue(job.invalidated)
    self.assertFalse(job.same_client)
    self.assertEqual(job.seconds.seconds, 0)
    self.assertEqual(job.client, None)
    self.assertEqual(job.status, models.JobStatus.NOT_STARTED)

    post_data = {'same_client':'on'}
    utils.create_step_result(job=job)
    job.client = client
    job.save()
    response = self.client.post(url, data=post_data)
    self.assertEqual(response.status_code, 302) #redirect
    job.refresh_from_db()
    self.assertRedirects(response, redir_url)
    self.assertEqual(job.step_results.count(), 0)
    self.assertFalse(job.complete)
    self.assertTrue(job.active)
    self.assertTrue(job.invalidated)
    self.assertTrue(job.same_client)
    self.assertEqual(job.seconds.seconds, 0)
    self.assertEqual(job.client, client)
    self.assertEqual(job.status, models.JobStatus.NOT_STARTED)

  def test_view_profile(self):
    # invalid git server
    response = self.client.get(reverse('ci:view_profile', args=[1000]))
    self.assertEqual(response.status_code, 404)

    # not signed in should redirect to sign in
    server = utils.create_git_server()
    response = self.client.get(reverse('ci:view_profile', args=[server.host_type]))
    self.assertEqual(response.status_code, 302) # redirect

    user = utils.get_test_user()
    repo1 = utils.create_repo(name='repo1', user=user)
    repo2 = utils.create_repo(name='repo2', user=user)
    repo3 = utils.create_repo(name='repo3', user=user)
    utils.create_recipe(name='r1', user=user, repo=repo1)
    utils.create_recipe(name='r2', user=user, repo=repo2)
    utils.create_recipe(name='r3', user=user, repo=repo3)
    # signed in
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

    settings.COLLABORATOR_CACHE_TIMEOUT = 0 #don't want the cache turned on
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
    # A collaborator
    response = self.client.post(reverse('ci:activate_job', args=[job.pk]))
    job = models.Job.objects.get(pk=job.pk)
    self.assertEqual(response.status_code, 302) # redirect
    self.assertTrue(job.active)

  def test_start_session(self):
    settings.DEBUG = True
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

    settings.DEBUG = False
    response = self.client.get(reverse('ci:start_session', args=[user.pk]))
    self.assertEqual(response.status_code, 404)

  def test_start_session_by_name(self):
    settings.DEBUG = True

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

    settings.DEBUG = False
    response = self.client.get(reverse('ci:start_session_by_name', args=[user.name]))
    self.assertEqual(response.status_code, 404)

  @patch.object(models.GitUser, 'start_session')
  @patch.object(api.GitHubAPI, 'last_sha')
  def test_manual(self, last_sha_mock, user_mock):
    last_sha_mock.return_value = '1234'
    self.set_counts()
    response = self.client.get(reverse('ci:manual_branch', args=[1000,1000]))
    # only post allowed
    self.assertEqual(response.status_code, 405)
    self.compare_counts()

    other_branch = utils.create_branch(name="other", repo=self.repo)
    # no recipes for that branch
    user_mock.return_value = self.build_user.server.auth().start_session_for_user(self.build_user)
    url = reverse('ci:manual_branch', args=[self.build_user.build_key, other_branch.pk])
    self.set_counts()
    response = self.client.post(url)
    self.assertEqual(response.status_code, 200)
    self.assertIn('Success', response.content)
    self.compare_counts()

    # branch exists, jobs will get created
    url = reverse('ci:manual_branch', args=[self.build_user.build_key, self.branch.pk])
    self.set_counts()
    response = self.client.post(url)
    self.assertEqual(response.status_code, 200)
    self.assertIn('Success', response.content)
    self.compare_counts(jobs=1, events=1, ready=1, commits=1, active=1)

    response = self.client.post( url, {'next': reverse('ci:main'), })
    self.assertEqual(response.status_code, 302) # redirect

    user_mock.side_effect = Exception
    response = self.client.post(url)
    self.assertIn('Error', response.content)

  def test_get_job_results(self):
    # bad pk
    url = reverse('ci:job_results', args=[1000])
    response = self.client.get(url)
    self.assertEqual(response.status_code, 404)

    user = utils.get_test_user()
    job = utils.create_job(user=user)
    step = utils.create_step(recipe=job.recipe, filename='common/1.sh')
    utils.create_step_result(job=job, step=step)
    utils.create_step_environment(step=step)
    url = reverse('ci:job_results', args=[job.pk])
    response = self.client.get(url)
    # owner doesn't have permission
    self.assertEqual(response.status_code, 403)

    utils.simulate_login(self.client.session, user)
    response = self.client.get(url)
    self.assertEqual(response.status_code, 200)

  @patch.object(api.GitHubAPI, 'is_collaborator')
  def test_job_script(self, mock_collab):
    # bad pk
    mock_collab.return_value = False
    response = self.client.get(reverse('ci:job_script', args=[1000]))
    self.assertEqual(response.status_code, 404)

    user = utils.get_test_user()
    job = utils.create_job(user=user)
    job.recipe.build_user = user
    job.recipe.save()
    utils.create_prestepsource(recipe=job.recipe)
    utils.create_recipe_environment(recipe=job.recipe)
    step = utils.create_step(recipe=job.recipe, filename='scripts/1.sh')
    utils.create_step_environment(step=step)

    url = reverse('ci:job_script', args=[job.pk])
    response = self.client.get(url)
    # owner doesn't have permission
    self.assertEqual(response.status_code, 404)

    mock_collab.return_value = True
    utils.simulate_login(self.client.session, user)
    response = self.client.get(url)
    self.assertEqual(response.status_code, 200)
    self.assertIn(job.recipe.name, response.content)

  def test_mooseframework(self):
    # no moose repo
    response = self.client.get(reverse('ci:mooseframework'))
    self.assertEqual(response.status_code, 200)

    user = utils.create_user(name='idaholab')
    repo = utils.create_repo(name='moose', user=user)
    utils.create_pr(repo=repo)
    # no master/devel branches
    response = self.client.get(reverse('ci:mooseframework'))
    self.assertEqual(response.status_code, 200)
    utils.create_branch(name='master', repo=repo)
    utils.create_branch(name='devel', repo=repo)
    # should be good
    response = self.client.get(reverse('ci:mooseframework'))
    self.assertEqual(response.status_code, 200)

  def test_scheduled(self):
    utils.create_event()
    response = self.client.get(reverse('ci:scheduled'))
    self.assertEqual(response.status_code, 200)
