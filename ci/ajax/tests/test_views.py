# -*- coding: utf-8 -*-

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
from django.urls import reverse
from django.utils.html import escape
from ci.tests import utils
from mock import patch
from ci.github import api
from ci import models, Permissions
from ci.tests import DBTester
from django.test import override_settings

@override_settings(INSTALLED_GITSERVERS=[utils.github_config()])
class Tests(DBTester.DBTester):
    @patch.object(api.GitHubAPI, 'is_collaborator')
    @override_settings(COLLABORATOR_CACHE_TIMEOUT=0)
    def test_get_result_output(self, mock_is_collaborator):
        mock_is_collaborator.return_value = False
        url = reverse('ci:ajax:get_result_output')
        # no parameters
        response = self.client.get(url)
        self.assertEqual(response.status_code, 400)

        result = utils.create_step_result()
        result.output = 'output'
        result.save()
        result.job.recipe.private = False
        result.job.recipe.save()
        data = {'result_id': result.pk}

        # should be ok since recipe isn't private
        response = self.client.get(url, data)
        self.assertEqual(response.status_code, 200)
        json_data = response.json()
        self.assertIn(result.output, json_data["contents"])

        result.job.recipe.private = True
        result.job.recipe.save()

        # recipe is private and not signed in, shouldn't see it
        response = self.client.get(url, data)
        self.assertEqual(response.status_code, 403)

        user = utils.get_test_user()
        utils.simulate_login(self.client.session, user)
        # recipe is private, not a collaborator
        response = self.client.get(url, data)
        self.assertEqual(response.status_code, 403)

        mock_is_collaborator.return_value = True
        # recipe is private, but a collaborator
        response = self.client.get(url, data)
        self.assertEqual(response.status_code, 200)
        json_data = response.json()
        self.assertIn(result.output, json_data["contents"])

    def test_pr_update(self):
        url = reverse('ci:ajax:pr_update', args=[1000])
        # bad pr
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)

        pr = utils.create_pr(title="Foo <type> & bar …")
        url = reverse('ci:ajax:pr_update', args=[pr.pk])

        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        json_data = response.json()
        self.assertIn('events', json_data)

    def test_event_update(self):
        ev = utils.create_event()
        url = reverse('ci:ajax:event_update', args=[1000])
        # no parameters
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)

        url = reverse('ci:ajax:event_update', args=[ev.pk])

        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        json_data = response.json()
        self.assertIn('events', json_data)

    def test_main_update(self):
        url = reverse('ci:ajax:main_update')
        # no parameters
        response = self.client.get(url)
        self.assertEqual(response.status_code, 400)

        pr_open = utils.create_pr(title='Foo <type> & bar …', number=1)
        ev_open = utils.create_event()
        pr_open.closed = False
        pr_open.save()
        ev_open.pull_request = pr_open
        ev_open.save()
        pr_closed = utils.create_pr(title='closed_pr', number=2)
        pr_closed.closed = True
        pr_closed.save()
        ev_closed = utils.create_event(commit1='2345')
        ev_closed.pull_request = pr_closed
        ev_closed.save()
        pr_open.repository.active = True
        pr_open.repository.save()

        ev_branch = utils.create_event(commit1='1', commit2='2', cause=models.Event.PUSH)
        ev_branch.base.branch.status = models.JobStatus.RUNNING
        ev_branch.base.branch.save()
        recipe, depends_on = utils.create_recipe_dependency()
        utils.create_job(recipe=recipe)
        utils.create_job(recipe=depends_on)

        data = {'last_request': 10, 'limit': 30}
        response = self.client.get(url, data)
        self.assertEqual(response.status_code, 200)
        json_data = response.json()
        self.assertIn('repo_status', json_data)
        self.assertIn('closed', json_data)
        self.assertEqual(len(json_data['repo_status']), 1)
        self.assertEqual(len(json_data['repo_status'][0]['prs']), 1)
        self.assertIn(escape(pr_open.title), json_data['repo_status'][0]['prs'][0]['description'])
        self.assertEqual(pr_closed.pk, json_data['closed'][0]['id'])

    @patch.object(api.GitHubAPI, 'is_collaborator')
    @patch.object(Permissions, 'is_allowed_to_see_clients')
    def test_job_results(self, mock_allowed, mock_is_collaborator):
        mock_is_collaborator.return_value = False
        mock_allowed.return_value = True
        url = reverse('ci:ajax:job_results')
        # no parameters
        response = self.client.get(url)
        self.assertEqual(response.status_code, 400)

        client = utils.create_client()
        step_result = utils.create_step_result()
        step_result.complete = True
        step_result.save()
        step_result.job.save()

        data = {'last_request': 10, 'job_id': 0 }
        # not signed in, not a collaborator
        response = self.client.get(url, data)
        self.assertEqual(response.status_code, 404)
        data['job_id'] = step_result.job.pk
        recipe = step_result.job.recipe
        recipe.private = True
        recipe.save()
        # not signed in, not a collaborator on a private recipe
        response = self.client.get(url, data)
        self.assertEqual(response.status_code, 403)

        recipe.private = False
        recipe.save()
        # recipe no longer private, should work
        response = self.client.get(url, data)
        self.assertEqual(response.status_code, 200)
        json_data = response.json()
        self.assertEqual(json_data['job_info']['client_name'], '')
        self.assertEqual(json_data['job_info']['client_url'], '')

        user = utils.get_test_user()
        utils.simulate_login(self.client.session, user)
        mock_is_collaborator.return_value = True
        recipe.private = True
        recipe.save()

        job = step_result.job
        job.client = client
        job.save()

        # should work now
        response = self.client.get(url, data)
        self.assertEqual(response.status_code, 200)
        json_data = response.json()
        self.assertIn('job_info', json_data)
        self.assertIn('results', json_data)
        self.assertEqual(step_result.job.pk, json_data['job_info']['id'])
        self.assertEqual(step_result.pk, json_data['results'][0]['id'])
        self.assertEqual(json_data['job_info']['client_name'], client.name)

        # should work now but return no results since nothing has changed
        data['last_request'] = json_data['last_request']+10
        response = self.client.get(url, data)
        self.assertEqual(response.status_code, 200)
        json_data = response.json()
        self.assertIn('job_info', json_data)
        self.assertIn('results', json_data)
        # job_info is always returned
        self.assertNotEqual('', json_data['job_info'])
        self.assertEqual([], json_data['results'])
        self.assertEqual(json_data['job_info']['client_name'], '')

    def test_repo_update(self):
        url = reverse('ci:ajax:repo_update')
        # no parameters
        response = self.client.get(url)
        self.assertEqual(response.status_code, 400)

        pr_open = utils.create_pr(title='Foo <type> & bar …', number=1)
        ev_open = utils.create_event()
        pr_open.closed = False
        pr_open.save()
        ev_open.pull_request = pr_open
        ev_open.save()
        pr_closed = utils.create_pr(title='closed_pr', number=2)
        pr_closed.closed = True
        pr_closed.save()
        ev_closed = utils.create_event(commit1='2345')
        ev_closed.pull_request = pr_closed
        ev_closed.save()
        pr_open.repository.active = True
        pr_open.repository.save()

        ev_branch = utils.create_event(commit1='1', commit2='2', cause=models.Event.PUSH)
        ev_branch.base.branch.status = models.JobStatus.RUNNING
        ev_branch.base.branch.save()
        recipe, depends_on = utils.create_recipe_dependency()
        utils.create_job(recipe=recipe)
        utils.create_job(recipe=depends_on)

        data = {'last_request': 10, 'limit': 30}
        # missing repo id
        response = self.client.get(url, data)
        self.assertEqual(response.status_code, 400)

        data["repo_id"] = pr_open.repository.pk
        response = self.client.get(url, data)
        self.assertEqual(response.status_code, 200)
        json_data = response.json()
        self.assertIn('repo_status', json_data)
        self.assertIn('closed', json_data)
        self.assertEqual(len(json_data['repo_status']), 1)
        self.assertEqual(len(json_data['repo_status'][0]['prs']), 1)
        self.assertIn(escape(pr_open.title), json_data['repo_status'][0]['prs'][0]['description'])
        self.assertEqual(pr_closed.pk, json_data['closed'][0]['id'])


    @patch.object(Permissions, 'is_allowed_to_see_clients')
    def test_clients_update(self, mock_allowed):
        mock_allowed.return_value = False
        url = reverse('ci:ajax:clients')
        # no parameters
        response = self.client.get(url)
        self.assertEqual(response.status_code, 400)

        mock_allowed.return_value = True
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        json_data = response.json()
        self.assertIn('clients', json_data)

    def test_repo_branches_status(self):
        # bad repo
        url = reverse('ci:ajax:repo_branches_status', args=["foo", "bar"])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)

        # branch not active
        branch = utils.create_branch()
        url = reverse('ci:ajax:repo_branches_status', args=[branch.repository.user.name, branch.repository.name])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        json_data = response.json()
        self.assertEqual(len(json_data["branches"]), 0)

        # should be OK
        branch.status = models.JobStatus.RUNNING
        branch.save()
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        json_data = response.json()
        self.assertEqual(len(json_data["branches"]), 1)
        self.assertEqual(json_data["branches"][0]["name"], branch.name)
        self.assertEqual(json_data["branches"][0]["status"], branch.status_slug())


    def test_repo_prs_status(self):
        # bad repo
        url = reverse('ci:ajax:repo_prs_status', args=["foo", "bar"])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)

        # not open
        pr = utils.create_pr()
        pr.closed = True
        pr.save()
        url = reverse('ci:ajax:repo_prs_status', args=[pr.repository.user.name, pr.repository.name])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        json_data = response.json()
        self.assertEqual(len(json_data["prs"]), 0)

        # should be OK
        pr.closed = False
        pr.save()
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        json_data = response.json()
        self.assertEqual(len(json_data["prs"]), 1)
        self.assertEqual(json_data["prs"][0]["number"], pr.number)
        self.assertEqual(json_data["prs"][0]["status"], pr.status_slug())

    def test_user_open_prs(self):
        user = utils.create_user()
        url = reverse('ci:ajax:user_open_prs', args=["no_exist"])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 400)

        url = reverse('ci:ajax:user_open_prs', args=[user.name])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 400)

        get_data = {'last_request': 10}
        response = self.client.get(url, get_data)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data["repos"]), 0)
        self.assertEqual(len(data["prs"]), 0)
        self.assertEqual(len(data["events"]), 0)
        self.assertEqual(len(data["changed_events"]), 0)
        self.assertEqual(len(data["repo_status"]), 0)

        ev = utils.create_event()
        pr = utils.create_pr()
        pr.closed = True
        pr.username = user.name
        pr.save()
        ev.pull_request = pr
        ev.save()
        utils.create_job(event=ev)

        # not open
        response = self.client.get(url, get_data)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data["repos"]), 0)
        self.assertEqual(len(data["prs"]), 0)
        self.assertEqual(len(data["events"]), 0)
        self.assertEqual(len(data["changed_events"]), 0)
        self.assertEqual(len(data["repo_status"]), 0)

        # should be OK
        pr.closed = False
        pr.save()
        response = self.client.get(url, get_data)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data["repos"]), 1)
        self.assertEqual(len(data["prs"]), 1)
        self.assertEqual(len(data["events"]), 1)
        self.assertEqual(len(data["changed_events"]), 1)
        self.assertEqual(len(data["repo_status"]), 1)

        # use the last request. The changed_* shouldn't be set
        get_data["last_request"] = data["last_request"] + 10
        response = self.client.get(url, get_data)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data["repos"]), 1)
        self.assertEqual(len(data["prs"]), 1)
        self.assertEqual(len(data["events"]), 1)
        self.assertEqual(len(data["changed_events"]), 0)
        self.assertEqual(len(data["repo_status"]), 0)
