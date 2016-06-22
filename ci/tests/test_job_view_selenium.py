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
  @patch.object(Permissions, 'is_allowed_to_see_clients')
  def test_update_status(self, mock_allowed):
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
  def test_update_results(self):
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
  def test_cancel_invalid(self, mock_allowed):
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
  def test_cancel_valid(self, mock_allowed):
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
  def test_invalidate_invalid(self, mock_allowed):
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
  def test_invalidate_valid(self, mock_allowed):
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
  def test_activate(self, mock_allowed):
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
    self.wait_for_js(wait=5)
    self.check_job(job)
