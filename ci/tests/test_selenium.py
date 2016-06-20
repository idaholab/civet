import SeleniumTester
import utils
from ci import models
from ci import Permissions
from ci.client import views as client_views
from mock import patch
from django.core.urlresolvers import reverse
from django.test import override_settings
from datetime import timedelta

class Tests(SeleniumTester.SeleniumTester):
  @SeleniumTester.test_drivers()
  def test_main_nothing(self):
    self.get()
    self.assertEqual(self.selenium.title, "Civet Home")
    self.check_repos()
    self.check_events()

  @SeleniumTester.test_drivers()
  def test_main_repo_update_all(self):
    repo, branch = self.create_repo_with_prs()
    self.get()
    self.check_repos()
    self.check_events()
    self.wait_for_js()

    branch.status = models.JobStatus.SUCCESS
    branch.save()
    for pr in repo.pull_requests.all():
      pr.status = models.JobStatus.SUCCESS
      pr.title = "New title"
      pr.number = pr.number + 100
      pr.username = "foobar"
      pr.save()
    self.wait_for_js()
    self.check_js_error()
    self.check_repos()
    self.check_events()

  @SeleniumTester.test_drivers()
  def test_main_repo_update_branch(self):
    repo, branch = self.create_repo_with_prs()
    self.get()
    self.check_repos()
    self.check_events()
    # need to sleep so that last_modified will trigger
    self.wait_for_js()

    branch.status = models.JobStatus.SUCCESS
    branch.save()
    self.wait_for_js()
    self.check_js_error()
    self.check_repos()
    self.check_events()

  @SeleniumTester.test_drivers()
  def test_main_repo_update_pr(self):
    repo, branch = self.create_repo_with_prs()
    self.get()
    self.check_repos()
    self.check_events()
    self.wait_for_js()

    pr = repo.pull_requests.last()
    pr.status = models.JobStatus.SUCCESS
    pr.title = "New title"
    pr.number = pr.number + 100
    pr.username = "foobar"
    pr.save()
    self.wait_for_js()
    self.check_js_error()
    self.check_repos()
    self.check_events()

  @SeleniumTester.test_drivers()
  def test_main_new_repo(self):
    repo, branch = self.create_repo_with_prs()
    self.get()
    self.check_repos()
    self.check_events()
    self.wait_for_js()
    repo2, branch2 = self.create_repo_with_prs(name="repo2")
    self.wait_for_js()
    self.check_js_error()
    self.check_repos()
    self.check_events()

  @SeleniumTester.test_drivers()
  def test_main_new_branch(self):
    repo, branch = self.create_repo_with_prs()
    self.get()
    self.check_repos()
    self.check_events()
    self.wait_for_js()

    branch2 = utils.create_branch(name="branch2", repo=repo)
    branch2.status = models.JobStatus.SUCCESS
    branch2.save()
    self.wait_for_js()
    self.check_js_error()
    self.check_repos()
    self.check_events()

  @SeleniumTester.test_drivers()
  def test_main_new_pr(self):
    repo, branch = self.create_repo_with_prs()
    self.get()
    self.check_repos()
    self.check_events()

    pr = utils.create_pr(repo=repo, number=100)
    pr.status = models.JobStatus.RUNNING
    pr.save()
    self.wait_for_js()
    self.check_js_error()
    self.check_repos()
    self.check_events()

  @SeleniumTester.test_drivers()
  def test_main_close_pr(self):
    repo, branch = self.create_repo_with_prs()
    self.get()
    self.check_repos()
    self.check_events()

    pr = repo.pull_requests.first()
    pr.closed = True
    pr.save()
    self.wait_for_js()
    self.check_js_error()
    self.check_repos()
    self.check_events()

  @SeleniumTester.test_drivers()
  def test_main_event_update(self):
    ev = self.create_event_with_jobs()
    self.get()
    self.check_repos()
    self.check_events()

    ev.status = models.JobStatus.SUCCESS
    ev.save()
    for job in ev.jobs.all():
      job.status = models.JobStatus.SUCCESS
      job.failed_step = "Failed"
      job.invalidated = True
      job.save()
    self.wait_for_js()
    self.check_js_error()
    self.check_repos()
    self.check_events()

  @SeleniumTester.test_drivers()
  def test_main_new_event(self):
    self.create_event_with_jobs()
    self.get()
    self.check_repos()
    self.check_events()

    self.create_event_with_jobs(commit='4321')
    self.wait_for_js()
    self.check_js_error()
    self.check_repos()
    self.check_events()

  @SeleniumTester.test_drivers()
  def test_main_event_new_job(self):
    self.create_event_with_jobs()
    self.get()
    self.check_repos()
    self.check_events()

    ev = models.Event.objects.first()
    r2 = utils.create_recipe(name="r2")
    ev.save() # to trigger the update
    utils.create_job(event=ev, recipe=r2)
    self.wait_for_js()
    self.check_js_error()
    self.check_repos()
    self.check_events()

  @SeleniumTester.test_drivers()
  def test_pr_update(self):
    ev = self.create_event_with_jobs()
    url = reverse('ci:view_pr', args=[ev.pull_request.pk])
    self.get(url)
    self.check_pr(ev.pull_request)
    self.check_events()

    ev.status = models.JobStatus.SUCCESS
    ev.save()
    ev.pull_request.closed = True
    ev.pull_request.status = models.JobStatus.FAILED
    ev.pull_request.save()

    for job in ev.jobs.all():
      job.status = models.JobStatus.SUCCESS
      job.failed_step = "Failed"
      job.invalidated = True
      job.save()
    self.wait_for_js()
    self.check_pr(ev.pull_request)
    self.check_events()

  @SeleniumTester.test_drivers()
  def test_pr_add_alt_recipe_invalid(self):
    ev = self.create_event_with_jobs()
    url = reverse('ci:view_pr', args=[ev.pull_request.pk])
    self.get(url)
    self.check_pr(ev.pull_request)
    self.check_events()

    # not signed in, can't see the form
    with self.assertRaises(Exception):
      self.selenium.find_element_by_id("alt_pr")

  @override_settings(DEBUG=True)
  @SeleniumTester.test_drivers()
  def test_pr_add_alt_recipe_valid(self):
    ev = self.create_event_with_jobs()
    start_session_url = reverse('ci:start_session', args=[ev.build_user.pk])
    self.get(start_session_url)
    url = reverse('ci:view_pr', args=[ev.pull_request.pk])
    self.get(url)
    self.check_pr(ev.pull_request)
    self.check_events()

    alt_pr_form = self.selenium.find_element_by_id("alt_pr")
    alt_recipe = ev.pull_request.alternate_recipes.first()
    choices = self.selenium.find_elements_by_xpath("//ul[@id='id_recipes']/li")
    self.assertEqual(len(choices), ev.pull_request.alternate_recipes.count())
    elem = self.selenium.find_element_by_xpath("//input[@value='%s']" % alt_recipe.pk)
    self.assertEqual(elem.get_attribute("checked"), "true")
    elem.click()
    self.wait_for_js()
    alt_pr_form.submit()
    self.wait_for_js()
    self.assertEqual(ev.pull_request.alternate_recipes.count(), 0)
    elem = self.selenium.find_element_by_xpath("//input[@value='%s']" % alt_recipe.pk)
    self.assertFalse(elem.get_attribute("checked"))

  @SeleniumTester.test_drivers()
  def test_event_update(self):
    ev = self.create_event_with_jobs()
    url = reverse('ci:view_event', args=[ev.pk])
    self.get(url)
    self.check_event(ev)
    self.check_events()

    ev.status = models.JobStatus.SUCCESS
    ev.complete = True
    ev.save()

    for job in ev.jobs.all():
      job.status = models.JobStatus.SUCCESS
      job.failed_step = "Failed"
      job.invalidated = True
      job.save()
    self.wait_for_js()
    self.check_event(ev)
    self.check_events()

  @SeleniumTester.test_drivers()
  @patch.object(Permissions, 'is_allowed_to_cancel')
  def test_event_cancel_invalid(self, mock_allowed):
    mock_allowed.return_value = (False, None)
    ev = self.create_event_with_jobs()
    url = reverse('ci:view_event', args=[ev.pk])
    self.get(url)
    self.check_event(ev)
    self.check_events()

    # not allowed to cancel
    with self.assertRaises(Exception):
      self.selenium.find_element_by_id("cancel_form")

  @SeleniumTester.test_drivers()
  @patch.object(Permissions, 'is_allowed_to_cancel')
  def test_event_cancel_valid(self, mock_allowed):
    mock_allowed.return_value = (True, None)
    ev = self.create_event_with_jobs()
    url = reverse('ci:view_event', args=[ev.pk])
    self.get(url)
    self.check_event(ev)
    self.check_events()

    cancel_form = self.selenium.find_element_by_id("cancel_form")
    cancel_form.submit()
    self.wait_for_load()
    self.wait_for_js()
    self.check_event(ev)
    self.check_events()

  @SeleniumTester.test_drivers()
  @patch.object(Permissions, 'is_allowed_to_cancel')
  def test_event_invalidate_invalid(self, mock_allowed):
    mock_allowed.return_value = (False, None)
    ev = self.create_event_with_jobs()
    url = reverse('ci:view_event', args=[ev.pk])
    self.get(url)
    self.check_event(ev)
    self.check_events()

    # not allowed to invalidate
    with self.assertRaises(Exception):
      self.selenium.find_element_by_id("invalidate_form")

  @SeleniumTester.test_drivers()
  @patch.object(Permissions, 'is_allowed_to_cancel')
  def test_event_invalidate_valid(self, mock_allowed):
    ev = self.create_event_with_jobs()
    mock_allowed.return_value = (True, ev.build_user)
    url = reverse('ci:view_event', args=[ev.pk])
    self.get(url)
    self.check_event(ev)
    self.check_events()

    cancel_form = self.selenium.find_element_by_id("invalidate_form")
    cancel_form.submit()
    self.wait_for_load()
    self.wait_for_js()
    self.check_event(ev)
    self.check_events()

  @SeleniumTester.test_drivers()
  @patch.object(Permissions, 'is_allowed_to_see_clients')
  def test_job_update_status(self, mock_allowed):
    mock_allowed.return_value = True
    ev = self.create_event_with_jobs()
    job = ev.jobs.first()
    url = reverse('ci:view_job', args=[job.pk])
    self.get(url)
    self.check_job(job)

    job.ready = True
    job.client = utils.create_client()
    job.save()
    job.recipe.private = False
    job.recipe.save()
    self.wait_for_js()
    self.check_js_error()
    # job wasn't ready so JS didn't update it
    with self.assertRaises(Exception):
      self.check_job(job)

    self.get(url)
    self.check_job(job)

    job.status = models.JobStatus.SUCCESS
    job.complete = True
    job.invalidated = True
    job.save()
    self.wait_for_js()
    self.check_job(job)

  @SeleniumTester.test_drivers()
  def test_job_update_results(self):
    ev = self.create_event_with_jobs()
    job = ev.jobs.first()
    job.ready = True
    job.save()
    job.recipe.private = False
    job.recipe.save()
    url = reverse('ci:view_job', args=[job.pk])
    self.get(url)
    self.check_job(job)
    client_views.get_job_info(job)
    self.wait_for_js()
    self.check_job(job)

    for result in job.step_results.all():
      result.status = models.JobStatus.SUCCESS
      result.output = "Output of %s" % result
      result.seconds = timedelta(seconds=10)
      result.exit_status = 10
      result.save()
      job.save()

    self.wait_for_js()
    self.check_job(job)

  @SeleniumTester.test_drivers()
  @override_settings(DEBUG=True)
  @override_settings(COLLABORATOR_CACHE_TIMEOUT=0)
  @patch.object(Permissions, 'is_collaborator')
  def test_job_cancel_invalid(self, mock_allowed):
    ev = self.create_event_with_jobs()
    start_session_url = reverse('ci:start_session', args=[ev.build_user.pk])
    self.get(start_session_url)
    mock_allowed.return_value = (False, None)
    job = ev.jobs.first()
    url = reverse('ci:view_job', args=[job.pk])
    self.get(url)
    self.check_job(job)
    # not allowed to cancel
    with self.assertRaises(Exception):
      self.selenium.find_element_by_id("cancel")

    mock_allowed.return_value = (True, ev.build_user)
    # should work now
    client_views.get_job_info(job)
    self.get(url)
    self.check_job(job)
    self.selenium.find_element_by_id("cancel")

    job.complete = True
    job.save()
    self.get(url)
    self.check_job(job)
    # job is complete, can't cancel
    with self.assertRaises(Exception):
      self.selenium.find_element_by_id("cancel")

    job.complete = False
    job.active = False
    job.save()
    self.get(url)
    self.check_job(job)
    # job is not active, can't cancel
    with self.assertRaises(Exception):
      self.selenium.find_element_by_id("cancel")

  @SeleniumTester.test_drivers()
  @override_settings(DEBUG=True)
  @override_settings(COLLABORATOR_CACHE_TIMEOUT=0)
  @patch.object(Permissions, 'is_collaborator')
  def test_job_cancel_valid(self, mock_allowed):
    ev = self.create_event_with_jobs()
    mock_allowed.return_value = (True, ev.build_user)
    start_session_url = reverse('ci:start_session', args=[ev.build_user.pk])
    self.get(start_session_url)
    job = ev.jobs.first()
    job.status = models.JobStatus.SUCCESS
    job.save()
    client_views.get_job_info(job)
    url = reverse('ci:view_job', args=[job.pk])
    self.get(url)
    self.check_job(job)
    cancel_elem = self.selenium.find_element_by_id("cancel")
    cancel_elem.submit()
    self.wait_for_js()
    self.check_job(job)

  @SeleniumTester.test_drivers()
  @override_settings(DEBUG=True)
  @override_settings(COLLABORATOR_CACHE_TIMEOUT=0)
  @patch.object(Permissions, 'is_collaborator')
  def test_job_invalidate_invalid(self, mock_allowed):
    mock_allowed.return_value = (False, None)
    ev = self.create_event_with_jobs()
    start_session_url = reverse('ci:start_session', args=[ev.build_user.pk])
    self.get(start_session_url)
    mock_allowed.return_value = (False, None)
    job = ev.jobs.first()
    url = reverse('ci:view_job', args=[job.pk])
    self.get(url)
    self.check_job(job)
    # not allowed to cancel
    with self.assertRaises(Exception):
      self.selenium.find_element_by_id("invalidate")

    # OK now
    mock_allowed.return_value = (True, ev.build_user)
    self.get(url)
    self.check_job(job)
    self.selenium.find_element_by_id("invalidate")

    # job now active, shouldn't be able to invalidate
    job.active = False
    job.save()
    self.get(url)
    self.check_job(job)
    with self.assertRaises(Exception):
      self.selenium.find_element_by_id("invalidate")

  @SeleniumTester.test_drivers()
  @override_settings(DEBUG=True)
  @override_settings(COLLABORATOR_CACHE_TIMEOUT=0)
  @patch.object(Permissions, 'is_collaborator')
  def test_job_invalidate_valid(self, mock_allowed):
    ev = self.create_event_with_jobs()
    start_session_url = reverse('ci:start_session', args=[ev.build_user.pk])
    self.get(start_session_url)
    mock_allowed.return_value = (True, ev.build_user)
    job = ev.jobs.first()
    job.status = models.JobStatus.SUCCESS
    job.complete = True
    job.save()
    client_views.get_job_info(job)
    for result in job.step_results.all():
      result.status = models.JobStatus.SUCCESS
      result.save()
    url = reverse('ci:view_job', args=[job.pk])
    self.get(url)
    self.check_job(job)
    elem = self.selenium.find_element_by_id("invalidate")
    elem.submit()
    self.wait_for_load()
    self.wait_for_js()
    self.check_job(job)

  @SeleniumTester.test_drivers()
  @override_settings(DEBUG=True)
  @override_settings(COLLABORATOR_CACHE_TIMEOUT=0)
  @patch.object(Permissions, 'is_collaborator')
  def test_job_activate(self, mock_allowed):
    mock_allowed.return_value = (False, None)
    ev = self.create_event_with_jobs()
    start_session_url = reverse('ci:start_session', args=[ev.build_user.pk])
    self.get(start_session_url)
    job = ev.jobs.first()
    job.active = False
    job.save()
    url = reverse('ci:view_job', args=[job.pk])
    self.get(url)
    self.check_job(job)
    with self.assertRaises(Exception):
      self.selenium.find_element_by_id("job_active_form")

    mock_allowed.return_value = (True, ev.build_user)

    self.get(url)
    self.check_job(job)
    elem = self.selenium.find_element_by_id("job_active_form")
    elem.submit()
    self.wait_for_load()
    self.wait_for_js(wait=10)
    self.check_job(job)


  @SeleniumTester.test_drivers()
  def test_view_repo_basic(self):
    repo, branch = self.create_repo_with_prs()
    url = reverse('ci:view_repo', args=[repo.pk])
    self.get(url)
    self.check_repos()
    self.check_events()

  @SeleniumTester.test_drivers()
  def test_view_repo_repo_update_all(self):
    repo, branch = self.create_repo_with_prs()
    url = reverse('ci:view_repo', args=[repo.pk])
    self.get(url)
    self.check_repos()
    self.check_events()
    self.wait_for_js()

    branch.status = models.JobStatus.SUCCESS
    branch.save()
    for pr in repo.pull_requests.all():
      pr.status = models.JobStatus.SUCCESS
      pr.title = "New title"
      pr.number = pr.number + 100
      pr.username = "foobar"
      pr.save()
    self.wait_for_js()
    self.check_js_error()
    self.check_repos()
    self.check_events()

  @SeleniumTester.test_drivers()
  def test_view_repo_repo_update_branch(self):
    repo, branch = self.create_repo_with_prs()
    url = reverse('ci:view_repo', args=[repo.pk])
    self.get(url)
    self.check_repos()
    self.check_events()
    # need to sleep so that last_modified will trigger
    self.wait_for_js()

    branch.status = models.JobStatus.SUCCESS
    branch.save()
    self.wait_for_js()
    self.check_js_error()
    self.check_repos()
    self.check_events()

  @SeleniumTester.test_drivers()
  def test_view_repo_repo_update_pr(self):
    repo, branch = self.create_repo_with_prs()
    url = reverse('ci:view_repo', args=[repo.pk])
    self.get(url)
    self.check_repos()
    self.check_events()
    self.wait_for_js()

    pr = repo.pull_requests.last()
    pr.status = models.JobStatus.SUCCESS
    pr.title = "New title"
    pr.number = pr.number + 100
    pr.username = "foobar"
    pr.save()
    self.wait_for_js()
    self.check_js_error()
    self.check_repos()
    self.check_events()

  @SeleniumTester.test_drivers()
  def test_view_repo_new_branch(self):
    repo, branch = self.create_repo_with_prs()
    url = reverse('ci:view_repo', args=[repo.pk])
    self.get(url)
    self.check_repos()
    self.check_events()
    self.wait_for_js()

    branch2 = utils.create_branch(name="branch2", repo=repo)
    branch2.status = models.JobStatus.SUCCESS
    branch2.save()
    self.wait_for_js()
    self.check_js_error()
    self.check_repos()
    self.check_events()

  @SeleniumTester.test_drivers()
  def test_view_repo_new_pr(self):
    repo, branch = self.create_repo_with_prs()
    url = reverse('ci:view_repo', args=[repo.pk])
    self.get(url)
    self.check_repos()
    self.check_events()

    pr = utils.create_pr(repo=repo, number=100)
    pr.status = models.JobStatus.RUNNING
    pr.save()
    self.wait_for_js()
    self.check_js_error()
    self.check_repos()
    self.check_events()

  @SeleniumTester.test_drivers()
  def test_view_repo_close_pr(self):
    repo, branch = self.create_repo_with_prs()
    url = reverse('ci:view_repo', args=[repo.pk])
    self.get(url)
    self.check_repos()
    self.check_events()

    pr = repo.pull_requests.first()
    pr.closed = True
    pr.save()
    self.wait_for_js()
    self.check_js_error()
    self.check_repos()
    self.check_events()

  @SeleniumTester.test_drivers()
  def test_view_repo_event_update(self):
    ev = self.create_event_with_jobs()
    url = reverse('ci:view_repo', args=[ev.base.branch.repository.pk])
    self.get(url)
    self.check_repos()
    self.check_events()

    ev.status = models.JobStatus.SUCCESS
    ev.save()
    for job in ev.jobs.all():
      job.status = models.JobStatus.SUCCESS
      job.failed_step = "Failed"
      job.invalidated = True
      job.save()
    self.wait_for_js()
    self.check_js_error()
    self.check_repos()
    self.check_events()

  @SeleniumTester.test_drivers()
  def test_view_repo_new_event(self):
    ev = self.create_event_with_jobs()
    url = reverse('ci:view_repo', args=[ev.base.branch.repository.pk])
    self.get(url)
    self.check_repos()
    self.check_events()

    self.create_event_with_jobs(commit='4321')
    self.wait_for_js()
    self.check_js_error()
    self.check_repos()
    self.check_events()

  @SeleniumTester.test_drivers()
  def test_view_repo_event_new_job(self):
    ev = self.create_event_with_jobs()
    url = reverse('ci:view_repo', args=[ev.base.branch.repository.pk])
    self.get(url)
    self.check_repos()
    self.check_events()

    ev = models.Event.objects.first()
    r2 = utils.create_recipe(name="r2")
    ev.save() # to trigger the update
    utils.create_job(event=ev, recipe=r2)
    self.wait_for_js()
    self.check_js_error()
    self.check_repos()
    self.check_events()
