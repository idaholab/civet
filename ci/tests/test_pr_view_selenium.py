
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

from __future__ import unicode_literals, absolute_import
import SeleniumTester
from ci import models
from django.urls import reverse
from django.test import override_settings
import utils

@override_settings(INSTALLED_GITSERVERS=[utils.github_config()])
class Tests(SeleniumTester.SeleniumTester):
    @SeleniumTester.test_drivers()
    def test_update(self):
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
    def test_add_alt_recipe_invalid(self):
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
    def test_add_alt_recipe_valid(self):
        ev = self.create_event_with_jobs()
        start_session_url = reverse('ci:start_session', args=[ev.build_user.pk])
        self.get(start_session_url)
        url = reverse('ci:view_pr', args=[ev.pull_request.pk])
        self.get(url)
        self.check_pr(ev.pull_request)
        self.check_events()

        alt_pr_form = self.selenium.find_element_by_id("alt_pr")
        alt_recipe = ev.pull_request.alternate_recipes.first()
        choices = self.selenium.find_elements_by_xpath("//input[@type='checkbox']")
        default_recipes = models.Recipe.objects.filter(cause=models.Recipe.CAUSE_PULL_REQUEST)
        self.assertEqual(len(choices), ev.pull_request.alternate_recipes.count() + len(default_recipes))
        elem = self.selenium.find_element_by_xpath("//input[@value='%s']" % alt_recipe.pk)
        self.assertEqual(elem.get_attribute("checked"), "true")
        elem.click()
        self.wait_for_js()
        alt_pr_form.submit()
        self.wait_for_js()
        self.assertEqual(ev.pull_request.alternate_recipes.count(), 0)
        elem = self.selenium.find_element_by_xpath("//input[@value='%s']" % alt_recipe.pk)
        self.assertFalse(elem.get_attribute("checked"))
