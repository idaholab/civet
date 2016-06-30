from django.core.urlresolvers import reverse
from django.conf import settings
from mock import patch
from ci import models, views, Permissions
from . import utils
from ci.github import api
import DBTester

class Tests(DBTester.DBTester):
  def setUp(self):
    super(Tests, self).setUp()
    self.old_servers = settings.INSTALLED_GITSERVERS
    settings.INSTALLED_GITSERVERS = [settings.GITSERVER_GITHUB]
    self.create_default_recipes()

  def tearDown(self):
    super(Tests, self).tearDown()
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

  @patch.object(api.GitHubAPI, 'is_collaborator')
  def test_view_pr(self, mock_collab):
    """
    testing ci:view_pr
    """
    # bad pr
    url = reverse('ci:view_pr', args=[1000,])
    response = self.client.get(url)
    self.assertEqual(response.status_code, 404)
    pr = utils.create_pr()
    ev = utils.create_event()
    ev.pull_request = pr
    ev.save()

    user = utils.get_test_user()
    utils.simulate_login(self.client.session, user)

    # user not a collaborator, no alternate recipe form
    mock_collab.return_value = False
    url = reverse('ci:view_pr', args=[pr.pk,])
    response = self.client.get(url)
    self.assertEqual(response.status_code, 200)

    # user a collaborator, they get alternate recipe form
    mock_collab.return_value = True
    r0 = utils.create_recipe(name="Recipe 0", repo=ev.base.branch.repository, cause=models.Recipe.CAUSE_PULL_REQUEST_ALT)
    r1 = utils.create_recipe(name="Recipe 1", repo=ev.base.branch.repository, cause=models.Recipe.CAUSE_PULL_REQUEST_ALT)
    response = self.client.get(url)
    self.assertEqual(response.status_code, 200)

    self.set_counts()
    # post an invalid alternate recipe form
    response = self.client.post(url, {})
    self.assertEqual(response.status_code, 200)
    self.assertEqual(pr.alternate_recipes.count(), 0)
    self.compare_counts()

    # post a valid alternate recipe form
    self.set_counts()
    response = self.client.post(url, {"recipes": [r0.pk, r1.pk]})
    self.assertEqual(response.status_code, 200)
    self.assertEqual(pr.alternate_recipes.count(), 2)
    self.compare_counts(jobs=2, ready=2, active=2, num_pr_alts=2)

    # post again with the same recipes
    self.set_counts()
    response = self.client.post(url, {"recipes": [r0.pk, r1.pk]})
    self.assertEqual(response.status_code, 200)
    self.assertEqual(pr.alternate_recipes.count(), 2)
    self.compare_counts()

    # post again different recipes. We don't auto cancel jobs.
    self.set_counts()
    response = self.client.post(url, {"recipes": [r0.pk]})
    self.assertEqual(response.status_code, 200)
    self.assertEqual(pr.alternate_recipes.count(), 1)
    self.compare_counts(num_pr_alts=-1)

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
    utils.create_event(user=repo.user, branch1=branch, branch2=branch)
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
    self.assertEqual(response.status_code, 302) # redirect with error message

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
    self.assertEqual(response.status_code, 302) # redirect with error message

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

  def check_job_invalidated(self, job, same_client=False, client=None):
    job.refresh_from_db()
    self.assertEqual(job.step_results.count(), 0)
    self.assertFalse(job.complete)
    self.assertTrue(job.active)
    self.assertTrue(job.invalidated)
    self.assertEqual(job.same_client, same_client)
    self.assertEqual(job.seconds.seconds, 0)
    self.assertEqual(job.client, client)
    self.assertEqual(job.status, models.JobStatus.NOT_STARTED)

  @patch.object(Permissions, 'is_allowed_to_cancel')
  def test_invalidate_client(self, allowed_mock):
    job = utils.create_job()
    client = utils.create_client()
    client2 = utils.create_client(name="client2")
    allowed_mock.return_value = (True, job.event.build_user)
    url = reverse('ci:invalidate', args=[job.pk])
    post_data = {}
    self.set_counts()
    response = self.client.post(url, data=post_data)
    self.assertEqual(response.status_code, 302) #redirect
    self.compare_counts(ready=1, invalidated=1, num_changelog=1)
    self.check_job_invalidated(job)
    job.client = client
    job.save()

    self.set_counts()
    post_data["client_list"] = client.pk
    response = self.client.post(url, data=post_data)
    self.assertEqual(response.status_code, 302) #redirect
    self.compare_counts(num_changelog=1)
    self.check_job_invalidated(job, True, client)

    self.set_counts()
    post_data["client_list"] = client2.pk
    response = self.client.post(url, data=post_data)
    self.assertEqual(response.status_code, 302) #redirect
    self.compare_counts(num_changelog=1)
    self.check_job_invalidated(job, True, client2)

  @patch.object(Permissions, 'is_allowed_to_cancel')
  def test_invalidate(self, allowed_mock):
    # only post is allowed
    url = reverse('ci:invalidate', args=[1000])
    self.set_counts()
    response = self.client.get(url)
    self.assertEqual(response.status_code, 405) # not allowed
    self.compare_counts()

    # invalid job
    self.set_counts()
    response = self.client.post(url)
    self.assertEqual(response.status_code, 404) # not found
    self.compare_counts()

    # can't invalidate
    step_result = utils.create_step_result()
    job = step_result.job
    allowed_mock.return_value = (False, None)
    url = reverse('ci:invalidate', args=[job.pk])
    self.set_counts()
    response = self.client.post(url)
    self.assertEqual(response.status_code, 403) # forbidden
    self.compare_counts()

    # valid
    client = utils.create_client()
    job.client = client
    job.save()
    post_data = {'same_client':None}
    allowed_mock.return_value = (True, job.event.build_user)
    self.set_counts()
    response = self.client.post(url, data=post_data)
    self.assertEqual(response.status_code, 302) #redirect
    self.compare_counts(ready=1, invalidated=1, num_changelog=1)
    job.refresh_from_db()
    redir_url = reverse('ci:view_job', args=[job.pk])
    self.assertRedirects(response, redir_url)
    self.check_job_invalidated(job)

    post_data = {'same_client':'on'}
    utils.create_step_result(job=job)
    job.client = client
    job.save()
    self.set_counts()
    response = self.client.post(url, data=post_data)
    self.assertEqual(response.status_code, 302) #redirect
    self.compare_counts(num_changelog=1)
    job.refresh_from_db()
    self.assertRedirects(response, redir_url)
    self.check_job_invalidated(job, True, client)

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
    self.compare_counts(jobs=1, events=1, ready=1, commits=1, active=1, active_repos=1)

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

  def test_job_info_search(self):
    """
    testing ci:job_info_search
    """
    url = reverse('ci:job_info_search')
    # no options
    response = self.client.get(url)
    self.assertEqual(response.status_code, 200)

    job = utils.create_job()
    osversion, created = models.OSVersion.objects.get_or_create(name="os", version="1")
    job.operating_system = osversion
    job.save()
    mod0, created = models.LoadedModule.objects.get_or_create(name="mod0")
    mod1, created = models.LoadedModule.objects.get_or_create(name="mod1")
    job.loaded_modules.add(mod0)
    response = self.client.get(url, {'os_versions': [osversion.pk], 'modules': [mod0.pk]})
    self.assertEqual(response.status_code, 200)

  def test_get_user_repos_info(self):
    request = self.factory.get('/')
    request.session = self.client.session
    repos = []
    for i in range(3):
      repo = utils.create_repo(name="repo%s" % i)
      repo.active = True
      repo.save()
      branch = utils.create_branch(name="branch0", user=repo.user, repo=repo)
      branch.status = models.JobStatus.SUCCESS
      branch.save()
      utils.create_event(branch1=branch, branch2=branch, user=repo.user)
      repos.append(repo)

    # user not logged in
    repo_status, evinfo, default = views.get_user_repos_info(request)
    self.assertEqual(len(repo_status), 3)
    self.assertEqual(len(evinfo), 3)
    self.assertFalse(default)

    # user not logged in, default enforced
    request = self.factory.get('/?default')
    repo_status, evinfo, default = views.get_user_repos_info(request)
    self.assertEqual(len(repo_status), 3)
    self.assertEqual(len(evinfo), 3)
    self.assertTrue(default)

    request = self.factory.get('/')
    user = repos[0].user
    utils.simulate_login(self.client.session, user)
    request.session = self.client.session
    # user is logged in but no prefs set
    repo_status, evinfo, default = views.get_user_repos_info(request)
    self.assertEqual(len(repo_status), 3)
    self.assertEqual(len(evinfo), 3)
    self.assertFalse(default)

    # user is logged in, add repos to prefs
    for i in range(3):
      user.preferred_repos.add(repos[i])
      repo_status, evinfo, default = views.get_user_repos_info(request)
      self.assertEqual(len(repo_status), i+1)
      self.assertEqual(len(evinfo), i+1)
      self.assertFalse(default)

    # user has one pref but default is enforced
    user.preferred_repos.clear()
    user.preferred_repos.add(repos[0])
    request = self.factory.get('/?default')
    repo_status, evinfo, default = views.get_user_repos_info(request)
    self.assertEqual(len(repo_status), 3)
    self.assertEqual(len(evinfo), 3)
    self.assertTrue(default)

  def test_user_repo_settings(self):
    """
    testing ci:user_repo_settings
    """
    repos = []
    for i in range(3):
      repo = utils.create_repo(name="repo%s" % i)
      repo.active = True
      repo.save()
      repos.append(repo)
    # not signed in
    url = reverse('ci:user_repo_settings')
    self.set_counts()
    response = self.client.get(url)
    self.compare_counts()
    self.assertEqual(response.status_code, 200)
    self.assertNotIn("form", response.content)

    user = repos[0].user
    utils.simulate_login(self.client.session, user)
    self.set_counts()
    response = self.client.get(url)
    self.compare_counts()
    self.assertEqual(response.status_code, 200)
    self.assertIn("form", response.content)

    # post an invalid form
    self.set_counts()
    response = self.client.post(url, {})
    self.assertEqual(response.status_code, 200)
    self.compare_counts()

    # post a valid form
    self.set_counts()
    response = self.client.post(url, {"repositories": [repos[0].pk, repos[1].pk]})
    self.assertEqual(response.status_code, 200)
    self.assertEqual(user.preferred_repos.count(), 2)
    self.compare_counts(repo_prefs=2)

    # post again with the same recipes
    self.set_counts()
    response = self.client.post(url, {"repositories": [repos[2].pk]})
    self.assertEqual(response.status_code, 200)
    self.assertEqual(user.preferred_repos.count(), 1)
    self.compare_counts(repo_prefs=-1)
