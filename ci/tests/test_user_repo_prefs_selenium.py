
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
from ci.tests import SeleniumTester, utils
from django.core.urlresolvers import reverse
from django.test import override_settings

@override_settings(INSTALLED_GITSERVERS=[utils.github_config()])
class Tests(SeleniumTester.SeleniumTester):
    def create_repos(self):
        repos = []
        for i in range(3):
            repo = utils.create_repo(name="repo%s" % i)
            repo.active = True
            repo.save()
            repos.append(repo)
        return repos

    @SeleniumTester.test_drivers()
    def test_no_login(self):
        self.create_repos()
        url = reverse('ci:user_repo_settings')
        self.get(url)
        with self.assertRaises(Exception):
            self.selenium.find_element_by_id("repo_settings")

    @SeleniumTester.test_drivers()
    @override_settings(DEBUG=True)
    def test_valid(self):
        repos = self.create_repos()
        user = repos[0].user
        start_session_url = reverse('ci:start_session', args=[user.pk])
        self.get(start_session_url)
        self.wait_for_js()

        self.assertEqual(user.preferred_repos.count(), 0)
        url = reverse('ci:user_repo_settings')
        self.get(url)
        form = self.selenium.find_element_by_id("repo_settings")
        form.submit()
        self.wait_for_js()
        self.assertEqual(user.preferred_repos.count(), 0)

        for i in range(3):
            form = self.selenium.find_element_by_id("repo_settings")
            elem = self.selenium.find_element_by_xpath("//input[@value='%s']" % repos[i].pk)
            elem.click()
            form.submit()
            self.wait_for_js()
            self.assertEqual(user.preferred_repos.count(), i+1)
            pref_repos = [ repo for repo in user.preferred_repos.all() ]
            for j in range(i+1):
                self.assertEqual(pref_repos[j], repos[j])
