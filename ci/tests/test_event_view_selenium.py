
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

from __future__ import unicode_literals
import SeleniumTester
from django.test import override_settings
from ci import models
from ci import Permissions
from mock import patch
from django.urls import reverse
import utils

@override_settings(INSTALLED_GITSERVERS=[utils.github_config()])
class Tests(SeleniumTester.SeleniumTester):
    @SeleniumTester.test_drivers()
    def test_update(self):
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
    @patch.object(Permissions, 'is_collaborator')
    def test_cancel_invalid(self, mock_collab):
        mock_collab.return_value = False
        ev = self.create_event_with_jobs()
        url = reverse('ci:view_event', args=[ev.pk])
        self.get(url)
        self.check_event(ev)
        self.check_events()

        # not allowed to cancel
        with self.assertRaises(Exception):
            self.selenium.find_element_by_id("cancel_form")

    @SeleniumTester.test_drivers()
    @patch.object(Permissions, 'is_collaborator')
    def test_cancel_valid(self, mock_collab):
        mock_collab.return_value = True
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
    @patch.object(Permissions, 'is_collaborator')
    def test_invalidate_invalid(self, mock_collab):
        mock_collab.return_value = False
        ev = self.create_event_with_jobs()
        url = reverse('ci:view_event', args=[ev.pk])
        self.get(url)
        self.check_event(ev)
        self.check_events()

        # not allowed to invalidate
        with self.assertRaises(Exception):
            self.selenium.find_element_by_id("invalidate_form")

    @SeleniumTester.test_drivers()
    @patch.object(Permissions, 'is_collaborator')
    def test_invalidate_valid(self, mock_collab):
        ev = self.create_event_with_jobs()
        mock_collab.return_value = True
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
