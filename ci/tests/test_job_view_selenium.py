
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
    @patch.object(Permissions, 'is_allowed_to_see_clients')
    @patch.object(Permissions, 'can_see_results')
    def test_cancel_invalid(self, mock_results, mock_clients, mock_allowed):
        ev = self.create_event_with_jobs()
        user = utils.create_user_with_token(name="username")
        start_session_url = reverse('ci:start_session', args=[user.pk])
        self.get(start_session_url)
        mock_allowed.return_value = (False, None)
        mock_clients.return_value = True
        mock_results.return_value = False
        job = ev.jobs.first()
        url = reverse('ci:view_job', args=[job.pk])
        self.get(url)
        self.check_job(job)
        # not allowed to cancel
        with self.assertRaises(Exception):
            self.selenium.find_element_by_id("cancel")

        mock_allowed.return_value = (True, user)
        mock_results.return_value = True
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
    @patch.object(Permissions, 'is_allowed_to_see_clients')
    @patch.object(Permissions, 'can_see_results')
    def test_cancel_valid(self, mock_results, mock_clients, mock_allowed):
        user = utils.create_user_with_token(name="username")
        ev = self.create_event_with_jobs()
        mock_allowed.return_value = (True, user)
        mock_results.return_value = True
        mock_clients.return_value = False
        start_session_url = reverse('ci:start_session', args=[user.pk])
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
    @patch.object(Permissions, 'can_see_results')
    @patch.object(Permissions, 'is_allowed_to_see_clients') # just here to avoid call api.is_member
    def test_invalidate_invalid(self, mock_clients, mock_results, mock_allowed):
        mock_allowed.return_value = (False, None)
        mock_clients.return_value = False
        mock_results.return_value = False
        ev = self.create_event_with_jobs()
        user = utils.create_user_with_token(name="username")
        start_session_url = reverse('ci:start_session', args=[user.pk])
        self.get(start_session_url)
        job = ev.jobs.first()
        url = reverse('ci:view_job', args=[job.pk])
        self.get(url)
        self.check_job(job)
        # not allowed to cancel
        with self.assertRaises(Exception):
            self.selenium.find_element_by_id("invalidate")

        # OK now
        mock_allowed.return_value = (True, user)
        mock_results.return_value = True
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
    @patch.object(Permissions, 'can_see_results')
    @patch.object(Permissions, 'is_allowed_to_see_clients') # just here to avoid call api.is_member
    def test_invalidate_valid(self, mock_clients, mock_results, mock_allowed):
        ev = self.create_event_with_jobs()
        user = utils.create_user_with_token(name="username")
        start_session_url = reverse('ci:start_session', args=[user.pk])
        self.get(start_session_url)
        mock_allowed.return_value = (True, user)
        mock_clients.return_value = False
        mock_results.return_value = True
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
    @patch.object(Permissions, 'can_see_results')
    @patch.object(Permissions, 'is_allowed_to_see_clients') # just here to avoid call api.is_member
    def test_activate(self, mock_clients, mock_results, mock_allowed):
        mock_allowed.return_value = (False, None)
        mock_clients.return_value = False
        mock_results.return_value = False
        user = utils.create_user_with_token(name="username")
        ev = self.create_event_with_jobs()
        start_session_url = reverse('ci:start_session', args=[user.pk])
        self.get(start_session_url)
        job = ev.jobs.first()
        job.active = False
        job.save()
        url = reverse('ci:view_job', args=[job.pk])
        self.get(url)
        self.check_job(job)
        with self.assertRaises(Exception):
            self.selenium.find_element_by_id("job_active_form")

        mock_allowed.return_value = (True, user)
        mock_results.return_value = True

        self.get(url)
        self.check_job(job)
        elem = self.selenium.find_element_by_id("job_active_form")
        elem.submit()
        self.wait_for_load()
        self.wait_for_js(wait=5)
        self.check_job(job)
