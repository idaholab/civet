# Copyright 2016-2025 Battelle Energy Alliance, LLC
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
from ci.tests import SeleniumTester, utils
from ci import models, Permissions
from selenium.webdriver.common.by import By
from django.urls import reverse
from django.test import override_settings
from mock import patch


@override_settings(INSTALLED_GITSERVERS=[utils.github_config()])
class Tests(SeleniumTester.SeleniumTester):
    def click(self, selector):
        elem = self.selenium.find_element(By.CSS_SELECTOR, selector)
        self.selenium.execute_script("arguments[0].click();", elem)

    @SeleniumTester.test_drivers()
    @patch.object(Permissions, "client_manager")
    @patch.object(Permissions, "can_manage_clients", return_value=True)
    @patch.object(Permissions, "is_allowed_to_see_clients", return_value=True)
    def test_select_all(self, mock_allowed, mock_manage, mock_manager):
        mock_manager.return_value = utils.get_test_user()
        for i in range(3):
            utils.create_client(name="client%s" % i)
        models.Client.objects.update(status=models.Client.IDLE)

        # Select all and disable
        self.get(reverse("ci:client_list"))
        self.click("#enabled_clients_form .select_all")
        self.click("#enabled_clients_form button[value='disable']")
        self.wait_for_load()
        self.assertEqual(models.Client.objects.filter(disabled=True).count(), 3)

        # Select all and enable
        self.click("#disabled_clients_form .select_all")
        self.click("#disabled_clients_form button[value='enable']")
        self.wait_for_load()
        self.assertEqual(models.Client.objects.filter(disabled=True).count(), 0)
