
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
from django.urls import reverse
from django.http import HttpResponseNotAllowed, HttpResponseBadRequest
from django.test import override_settings
import json
from mock import patch
from ci import models, Permissions
from ci.client import views
from ci.recipe import file_utils
from ci.tests import utils
from ci.github.api import GitHubAPI
from ci.client.tests import ClientTester

@override_settings(INSTALLED_GITSERVERS=[utils.github_config()])
class Tests(ClientTester.ClientTester):
    def test_client_ip(self):
        request = self.factory.get('/')
        request.META['REMOTE_ADDR'] = '1.1.1.1'
        ip = views.get_client_ip(request)
        self.assertEqual('1.1.1.1', ip)
        request.META['HTTP_X_FORWARDED_FOR'] = '2.2.2.2'
        ip = views.get_client_ip(request)
        self.assertEqual('2.2.2.2', ip)

    def test_get_jobs_cancel(self):
        user = utils.get_test_user()
        client = utils.create_client()
        request = self.factory.get('/')
        client_ip = views.get_client_ip(request)
        client.ip = client_ip
        client.save()
        url = reverse('ci:client:get_job')
        r0 = utils.create_recipe(name='recipe0', user=user)
        r1 = utils.create_recipe(name='recipe1', user=user)
        j0 = utils.create_job(user=user, recipe=r0)
        j1 = utils.create_job(user=user, recipe=r1)
        utils.update_job(j0, ready=True, active=True, status=models.JobStatus.NOT_STARTED)
        utils.update_job(j1, ready=True, active=True, status=models.JobStatus.NOT_STARTED)

        # get the first job
        post_data = {'client_name': client.name,
                     'build_keys': [user.build_key],
                     'build_configs': [j0.config.name]}
        self.set_counts()
        response = self.client_post_json(url, post_data)
        self.assertEqual(response.status_code, 200)
        self.compare_counts(active_branches=1)
        data = response.json()
        self.assertEqual(data['job_id'], j0.pk)
        self.assertEqual(data['status'], 'OK')

        # get the second job
        post_data = {'client_name': client.name,
                     'build_keys': [user.build_key],
                     'build_configs': [j1.config.name]}
        self.set_counts()
        response = self.client_post_json(url, post_data)
        self.assertEqual(response.status_code, 200)
        self.compare_counts(canceled=1, num_changelog=1, num_jobs_completed=1)
        data = response.json()
        self.assertEqual(data['job_id'], j1.pk)
        self.assertEqual(data['status'], 'OK')

        # first job should be cancelled
        j0.refresh_from_db()
        self.assertEqual(j0.status, models.JobStatus.CANCELED)

    def test_get_job_order(self):
        user = utils.get_test_user()
        jobs = []
        clients = []
        for i in range(6):
            recipe = utils.create_recipe(name=f'recipe{i}', user=user)
            job = utils.create_job(recipe=recipe, user=user)
            jobs.append(job)
            utils.update_job(job, ready=True, active=True)
            client = utils.create_client(name=f'client{i}')
            clients.append(client)
        jobs[0].recipe.priority = 1
        jobs[0].recipe.save()
        jobs[1].recipe.priority = 10
        jobs[1].recipe.save()
        jobs[2].recipe.priority = 5
        jobs[2].recipe.save()
        jobs[3].recipe.priority = 1
        jobs[3].recipe.save()
        jobs[4].recipe.priority = 1
        jobs[5].recipe.priority = 1
        jobs[4].set_prioritized('foo')
        jobs[5].set_prioritized('foo')

        # the order we expect to run jobs in
        expected_jobs = [jobs[5], jobs[4], jobs[1], jobs[2], jobs[0], jobs[3]]

        for i in range(4):
            url = reverse('ci:client:get_job')
            post_data = {'client_name': clients[i].name,
                         'build_keys': [user.build_key],
                         'build_configs': [jobs[i].config.name]}
            response = self.client_post_json(url, post_data)
            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertEqual(data['job_id'], expected_jobs[i].pk)

    def json_post_request(self, data):
        jdata = json.dumps(data)
        return self.factory.post('/', jdata, content_type='application/json')

    def client_post_json(self, url, data, client=None):
        jdata = json.dumps(data)
        return self.client.post(url, jdata, content_type='application/json')

    def test_check_post(self):
        # only post allowed
        request = self.factory.get('/')
        required = ['foo',]
        self.set_counts()
        data, response = views.check_post(request, required)
        self.compare_counts()
        self.assertEqual(data, None)
        self.assertTrue(isinstance(response, HttpResponseNotAllowed))

        # bad json decoding
        request = self.factory.post('/', {'bar': 'bar'}, content_type='text/html')
        self.set_counts()
        data, response = views.check_post(request, required)
        self.compare_counts()
        self.assertEqual(data, None)
        self.assertTrue(isinstance(response, HttpResponseBadRequest))

        # should be successful
        request = self.json_post_request({'foo': 'bar'})
        self.set_counts()
        data, response = views.check_post(request, required)
        self.compare_counts()
        self.assertNotEqual(data, None)
        self.assertEqual(None, response)

        # failed because we don't have the right data
        request = self.json_post_request({'bar': 'bar'})
        self.set_counts()
        data, response = views.check_post(request, required)
        self.compare_counts()
        self.assertNotEqual(data, None)
        self.assertTrue(isinstance(response, HttpResponseBadRequest))

    @patch.object(file_utils, 'get_contents')
    def test_get_job_info(self, contents_mock):
        with utils.RecipeDir():
            contents_mock.return_value = 'contents'
            user = utils.get_test_user()
            job = utils.create_job(user=user)
            utils.create_prestepsource(recipe=job.recipe)
            step = utils.create_step(recipe=job.recipe)
            utils.create_step_environment(step=step)
            utils.create_recipe_environment(recipe=job.recipe)
            self.assertEqual(job.recipe_repo_sha, "")
            self.set_counts()
            data = views.get_job_info(job)
            self.compare_counts()
            job.refresh_from_db()
            self.assertNotEqual(job.recipe_repo_sha, "")
            # hex shas are 40 characters
            self.assertEqual(len(job.recipe_repo_sha), 40)
            self.assertIn('recipe_name', data)
            self.assertIn('environment', data)
            self.assertIn('job_id', data)
            self.assertIn('prestep_sources', data)
            self.assertIn('steps', data)

    def test_get_job(self):
        user = utils.get_test_user()
        url = reverse('ci:client:get_job')

        post_data = {'client_name': 'testClient',
                     'build_keys': [user.build_key]}

        # only post allowed
        self.set_counts()
        response = self.client.get(url)
        self.compare_counts()
        self.assertEqual(response.status_code, 405) # not allowed

        # setup a ready job
        job = utils.create_job(user=user)
        job.ready = True
        job.active = True
        job.event.cause = models.Event.PULL_REQUEST
        pr = utils.create_pr()
        job.event.pull_request = pr
        job.event.save()
        job.status = models.JobStatus.NOT_STARTED
        job_id = job.pk
        job.save()

        # config does not exist, nothing there
        post_data['build_configs'] = ['testconfig']
        self.set_counts()
        response = self.client_post_json(url, post_data)
        self.compare_counts(num_clients=1)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['job_id'], None)

        # valid job, should be ok
        post_data['build_configs'] = [job.config.name]
        self.set_counts()
        response = self.client_post_json(url, post_data)
        self.compare_counts()
        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertEqual(data['job_id'], job_id)
        self.assertEqual(data['status'], 'OK')
        job.refresh_from_db()
        job.event.refresh_from_db()
        job.event.pull_request.refresh_from_db()
        self.assertEqual(job.status, models.JobStatus.RUNNING)
        self.assertEqual(job.event.status, models.JobStatus.RUNNING)
        self.assertEqual(job.event.pull_request.status, models.JobStatus.RUNNING)

        # create a job with a newer event.
        # This allows to test the update_status() function
        event2 = utils.create_event(commit1="2345", commit2="2345")
        job2 = utils.create_job(user=user, event=event2)
        job2.ready = True
        job2.active = True
        job2.event.cause = models.Event.PULL_REQUEST
        job2.event.pull_request = pr
        job2.event.save()
        job2.status = models.JobStatus.NOT_STARTED
        job2.save()
        job.status = models.JobStatus.NOT_STARTED
        job.client = None
        job.save()
        job.event.status = models.JobStatus.SUCCESS
        job.event.save()
        job.event.pull_request.status = models.JobStatus.SUCCESS
        job.event.pull_request.save()

        # valid job, should be ok, shouldn't update the status since
        # there is a newer event
        self.set_counts()
        response = self.client_post_json(url, post_data)
        self.compare_counts()
        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertEqual(data['job_id'], job_id)
        self.assertEqual(data['status'], 'OK')
        job.refresh_from_db()
        job.event.refresh_from_db()
        job.event.pull_request.refresh_from_db()
        self.assertEqual(job.status, models.JobStatus.RUNNING)
        self.assertEqual(job.event.status, models.JobStatus.RUNNING)
        # there is a newer event so this event doesn't update the PullRequest status
        self.assertEqual(job.event.pull_request.status, models.JobStatus.SUCCESS)

        # valid job, another client
        job.invalidated = True
        job.same_client = True
        job.status = models.JobStatus.NOT_STARTED
        client = utils.create_client(name='old_client')
        job.client = client
        job.save()

        # pull from previous client, should get other job
        self.set_counts()
        response = self.client_post_json(url, post_data)
        self.compare_counts()
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['job_id'], job2.pk)
        self.assertEqual(data['status'], 'OK')

        # pull from old_client, should get first job
        post_data['client_name'] = client.name
        self.set_counts()
        response = self.client_post_json(url, post_data)
        self.compare_counts()
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['job_id'], job.pk)
        self.assertEqual(data['status'], 'OK')

        # both jobs should be running
        for j in [job, job2]:
            j.refresh_from_db()
            j.event.refresh_from_db()
            j.event.pull_request.refresh_from_db()
            self.assertEqual(j.status, models.JobStatus.RUNNING)
            self.assertEqual(j.event.status, models.JobStatus.RUNNING)

    def test_job_finished_status(self):
        user = utils.get_test_user()
        recipe = utils.create_recipe(user=user)
        job = utils.create_job(recipe=recipe, user=user)
        step0 = utils.create_step(name='step0', recipe=recipe)
        step1 = utils.create_step(name='step1', recipe=recipe, position=1)
        step0_result = utils.create_step_result(step=step0, job=job)
        step1_result = utils.create_step_result(step=step1, job=job)
        step0_result.status = models.JobStatus.FAILED_OK
        step0_result.save()
        step1_result.status = models.JobStatus.SUCCESS
        step1_result.save()
        client = utils.create_client()
        job.client = client
        job.save()
        job.event.comments_url = 'http://localhost'
        job.event.pull_request = utils.create_pr()
        job.event.save()
        url = reverse('ci:client:job_finished', args=[user.build_key, client.name, job.pk])

        # A step has FAILED_OK
        # So final status is FAILED_OK and we update the PR
        post_data = {'seconds': 0, 'complete': True}
        with patch('ci.github.api.GitHubAPI') as mock_api:
            self.set_counts()
            response = self.client_post_json(url, post_data)
            self.compare_counts(num_events_completed=1, num_jobs_completed=1)
            self.assertEqual(response.status_code, 200)
            self.assertTrue(mock_api.called)
            self.assertTrue(mock_api.return_value.update_status.called)
            job.refresh_from_db()
            self.assertEqual(job.status, models.JobStatus.FAILED_OK)
            os_obj = models.OSVersion.objects.get(name="Other")
            self.assertEqual(job.operating_system.pk, os_obj.pk)
            self.assertEqual(job.loaded_modules.count(), 1)
            self.assertEqual(job.loaded_modules.first().name, "None")

        # A step FAILED
        # So final status is FAILED and we update the PR
        step0_result.status = models.JobStatus.FAILED
        step0_result.save()
        with patch('ci.github.api.GitHubAPI') as mock_api:
            self.set_counts()
            response = self.client_post_json(url, post_data)
            self.compare_counts()
            self.assertEqual(response.status_code, 200)
            self.assertTrue(mock_api.called)
            self.assertTrue(mock_api.return_value.update_status.called)
            job.refresh_from_db()
            self.assertEqual(job.status, models.JobStatus.FAILED)

        step0_result.status = models.JobStatus.SUCCESS
        step0_result.save()

        # All steps passed
        # So final status is SUCCESS and we update the PR
        with patch('ci.github.api.GitHubAPI') as mock_api:
            self.set_counts()
            response = self.client_post_json(url, post_data)
            self.compare_counts()
            self.assertEqual(response.status_code, 200)
            self.assertTrue(mock_api.called)
            self.assertTrue(mock_api.return_value.update_status.called)
            job.refresh_from_db()
            self.assertEqual(job.status, models.JobStatus.SUCCESS)

        step0_result.status = models.JobStatus.FAILED
        step0_result.save()

        # A step FAILED
        # So final status is FAILED and we update the PR
        with patch('ci.github.api.GitHubAPI') as mock_api:
            self.set_counts()
            response = self.client_post_json(url, post_data)
            self.compare_counts()
            self.assertEqual(response.status_code, 200)
            self.assertTrue(mock_api.called)
            self.assertTrue(mock_api.return_value.update_status.called)
            job.refresh_from_db()
            self.assertEqual(job.status, models.JobStatus.FAILED)

    def test_job_finished(self):
        user = utils.get_test_user()
        job = utils.create_job(user=user)
        step_result = utils.create_step_result(job=job)
        step_result.output = self.get_file("ubuntu_gcc_output.txt")
        step_result.save()
        client = utils.create_client()
        client2 = utils.create_client(name='other_client')
        job.client = client
        job.save()
        job.event.comments_url = 'http://localhost'
        job.event.save()

        post_data = {'seconds': 0, 'complete': True}
        url = reverse('ci:client:job_finished', args=[user.build_key, client.name, job.pk])

        # only post allowed
        self.set_counts()
        response = self.client.get(url)
        self.compare_counts()
        self.assertEqual(response.status_code, 405) # not allowed

        # bad url
        url = reverse('ci:client:job_finished', args=[user.build_key, client.name, 0])
        self.set_counts()
        response = self.client_post_json(url, post_data)
        self.compare_counts()
        self.assertEqual(response.status_code, 400) # bad request

        # unknown client
        url = reverse('ci:client:job_finished', args=[user.build_key, 'unknown_client', job.pk])
        self.set_counts()
        response = self.client_post_json(url, post_data)
        self.compare_counts()
        self.assertEqual(response.status_code, 400) # bad request

        # bad client
        url = reverse('ci:client:job_finished', args=[user.build_key, client2.name, job.pk])
        self.set_counts()
        response = self.client_post_json(url, post_data)
        self.compare_counts()
        self.assertEqual(response.status_code, 400) # bad request

        # should be ok
        url = reverse('ci:client:job_finished', args=[user.build_key, client.name, job.pk])
        self.set_counts()
        response = self.client_post_json(url, post_data)
        self.compare_counts(num_events_completed=1, num_jobs_completed=1)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn('message', data)
        self.assertEqual(data['status'], 'OK')
        job.refresh_from_db()
        self.assertTrue(job.complete)
        self.assertEqual(job.operating_system.name, "Ubuntu")
        self.assertEqual(job.operating_system.version, "14.04")
        self.assertEqual(job.operating_system.other, "trusty")
        self.check_modules(job, [ 'moose/.gcc_4.9.1',
            'moose/.tbb',
            'moose/.mpich-3.1.2_gcc',
            'moose/.mpich_petsc-3.6.3-gcc-superlu',
            'moose-tools',
            'moose/.ccache',
            'moose/.vtk-6',
            'moose-dev-gcc',
            ])

        job2 = utils.create_job(event=job.event)
        job2.ready = False
        job2.complete = False
        job2.status = models.JobStatus.NOT_STARTED
        job2.active = True
        job2.save()
        # should be ok. Make sure jobs get ready after one is finished.
        url = reverse('ci:client:job_finished', args=[user.build_key, client.name, job.pk])
        self.set_counts()
        response = self.client_post_json(url, post_data)
        self.compare_counts(ready=1)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn('message', data)
        self.assertEqual(data['status'], 'OK')
        job2 = models.Job.objects.get(pk=job2.pk)
        self.assertTrue(job2.ready)

    @patch.object(GitHubAPI, 'update_status')
    def test_job_finished_unrunnable(self, mock_status):
        user = utils.get_test_user()
        r0 = utils.create_recipe(name='recipe0', user=user)
        r1 = utils.create_recipe(name='recipe1', user=user)
        r2 = utils.create_recipe(name='recipe2', user=user)
        r2.depends_on.add(r1)
        r1.depends_on.add(r0)
        j0 = utils.create_job(user=user, recipe=r0)
        utils.create_job(user=user, recipe=r1)
        utils.create_job(user=user, recipe=r2)
        post_data = {'seconds': 0, 'complete': True}
        client = utils.create_client()
        j0.client = client
        j0.save()
        step_result = utils.create_step_result(job=j0)
        step_result.status = models.JobStatus.FAILED
        step_result.save()

        # should be ok
        url = reverse('ci:client:job_finished', args=[user.build_key, client.name, j0.pk])
        self.set_counts()
        response = self.client_post_json(url, post_data)
        self.compare_counts(num_events_completed=1, num_jobs_completed=1, active_branches=1)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(mock_status.call_count, 3) # 1 for the job complete update and 2 for the won't run update

        step_result.status = models.JobStatus.SUCCESS
        step_result.save()
        self.set_counts()
        response = self.client_post_json(url, post_data)
        self.compare_counts(ready=1)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(mock_status.call_count, 4) # 1 for the job complete update

    def test_start_step_result(self):
        user = utils.get_test_user()
        job = utils.create_job(user=user)
        result = utils.create_step_result(job=job)
        client = utils.create_client()
        client2 = utils.create_client(name='other_client')
        job.client = client
        job.event.cause = models.Event.PULL_REQUEST
        job.event.pr = utils.create_pr()
        job.event.save()
        job.save()

        post_data = {
            'step_num': result.position,
            'output': 'output',
            'time': 5,
            'complete': True,
            'exit_status': 0
            }
        url = reverse('ci:client:start_step_result', args=[user.build_key, client.name, result.pk])
        # only post allowed
        self.set_counts()
        response = self.client.get(url)
        self.compare_counts()
        self.assertEqual(response.status_code, 405) # not allowed

        # bad step result
        url = reverse('ci:client:start_step_result', args=[user.build_key, client.name, 0])
        self.set_counts()
        response = self.client_post_json(url, post_data)
        self.compare_counts()
        self.assertEqual(response.status_code, 400) # bad request

        # unknown client
        url = reverse('ci:client:start_step_result', args=[user.build_key, 'unknown_client', result.pk])
        self.set_counts()
        response = self.client_post_json(url, post_data)
        self.compare_counts()
        self.assertEqual(response.status_code, 400) # bad request

        # bad client
        url = reverse('ci:client:start_step_result', args=[user.build_key, client2.name, result.pk])
        self.set_counts()
        response = self.client_post_json(url, post_data)
        self.compare_counts()
        self.assertEqual(response.status_code, 400) # bad request

        # ok
        url = reverse('ci:client:start_step_result', args=[user.build_key, client.name, result.pk])
        self.set_counts()
        response = self.client_post_json(url, post_data)
        self.compare_counts()
        self.assertEqual(response.status_code, 200)
        result.refresh_from_db()
        self.assertEqual(result.status, models.JobStatus.RUNNING)
        data = response.json()
        self.assertEqual(data["command"], None)
        self.assertEqual(data["status"], "OK")

        # If a job got canceled, make sure it sends the command to the client
        job.status = models.JobStatus.CANCELED
        job.save()
        self.set_counts()
        response = self.client_post_json(url, post_data)
        self.compare_counts()
        self.assertEqual(response.status_code, 200)
        result.refresh_from_db()
        self.assertEqual(result.status, models.JobStatus.CANCELED)
        data = response.json()
        self.assertEqual(data["command"], "cancel")
        self.assertEqual(data["status"], "OK")

    def test_update_step_result(self):
        user = utils.get_test_user()
        job = utils.create_job(user=user)
        result = utils.create_step_result(job=job)
        client = utils.create_client()
        client2 = utils.create_client(name='other_client')
        job.client = client
        job.event.cause = models.Event.PULL_REQUEST
        job.status = models.JobStatus.RUNNING
        job.save()

        post_data = {
            'step_num': result.position,
            'output': 'output',
            'time': 5,
            'complete': True,
            'exit_status': 0
            }
        url = reverse('ci:client:update_step_result', args=[user.build_key, client.name, result.pk])
        # only post allowed
        self.set_counts()
        response = self.client.get(url)
        self.compare_counts()
        self.assertEqual(response.status_code, 405) # not allowed

        # bad step result
        url = reverse('ci:client:update_step_result', args=[user.build_key, client.name, 0])
        self.set_counts()
        response = self.client_post_json(url, post_data)
        self.compare_counts()
        self.assertEqual(response.status_code, 400) # bad request

        # unknown client
        url = reverse('ci:client:update_step_result', args=[user.build_key, 'unknown_client', result.pk])
        self.set_counts()
        response = self.client_post_json(url, post_data)
        self.compare_counts()
        self.assertEqual(response.status_code, 400) # bad request

        # bad client
        url = reverse('ci:client:update_step_result', args=[user.build_key, client2.name, result.pk])
        self.set_counts()
        response = self.client_post_json(url, post_data)
        self.compare_counts()
        self.assertEqual(response.status_code, 400) # bad request

        # ok
        url = reverse('ci:client:update_step_result', args=[user.build_key, client.name, result.pk])
        self.set_counts()
        response = self.client_post_json(url, post_data)
        self.compare_counts()
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "OK")
        self.assertEqual(data["command"], None)
        result.refresh_from_db()
        self.assertEqual(result.status, models.JobStatus.RUNNING)

        # test when the user invalidates a job while it is running
        job.status = models.JobStatus.NOT_STARTED
        job.save()
        self.set_counts()
        response = self.client_post_json(url, post_data)
        self.compare_counts()
        self.assertEqual(response.status_code, 200)
        result.refresh_from_db()
        data = response.json()
        self.assertEqual(result.status, models.JobStatus.NOT_STARTED)
        self.assertEqual(data["status"], "OK")
        self.assertEqual(data["command"], "cancel")

        # test when the user cancel a job while it is running
        job.status = models.JobStatus.CANCELED
        job.save()
        self.set_counts()
        response = self.client_post_json(url, post_data)
        self.compare_counts()
        self.assertEqual(response.status_code, 200)
        result.refresh_from_db()
        data = response.json()
        self.assertEqual(result.status, models.JobStatus.CANCELED)
        self.assertEqual(data["status"], "OK")
        self.assertEqual(data["command"], "cancel")

        # a step exited with nonzero, make sure we don't do the
        # next step
        job.status = models.JobStatus.RUNNING
        job.save()
        post_data['exit_status'] = 1
        self.set_counts()
        response = self.client_post_json(url, post_data)
        self.compare_counts()
        self.assertEqual(response.status_code, 200)
        result.refresh_from_db()
        self.assertEqual(result.exit_status, 1)
        self.assertEqual(result.status, models.JobStatus.RUNNING)

    def create_running_job(self):
        user = utils.get_test_user()
        job = utils.create_job(user=user)
        result = utils.create_step_result(job=job)
        client = utils.create_client()
        job.client = client
        job.event.cause = models.Event.PULL_REQUEST
        job.status = models.JobStatus.RUNNING
        job.save()
        return job, result

    def create_complete_step_result_post_data(self, step_num, output="output", time=5, complete=True, exit_status=0):
        return {
            'step_num': step_num,
            'output': output,
            'time': time,
            'complete': complete,
            'exit_status': exit_status,
            }

    def complete_step_result_url(self, job, build_key=None, name=None, pk=None):
        if not build_key:
            build_key = job.recipe.build_user.build_key
        if not name:
            name = job.client.name
        if pk == None:
            pk = job.step_results.first().pk

        return reverse('ci:client:complete_step_result', args=[build_key, name, pk])

    def test_complete_step_result_get(self):
        job, result = self.create_running_job()

        url = self.complete_step_result_url(job)
        # only post allowed
        self.set_counts()
        response = self.client.get(url)
        self.compare_counts()
        self.assertEqual(response.status_code, 405) # not allowed

    def test_complete_step_result_bad_result(self):
        job, result = self.create_running_job()
        post_data = self.create_complete_step_result_post_data(result.position)
        # bad step result
        url = self.complete_step_result_url(job, pk=0)
        self.set_counts()
        response = self.client_post_json(url, post_data)
        self.compare_counts()
        self.assertEqual(response.status_code, 400) # bad request

    def test_complete_step_result_unknown_client(self):
        job, result = self.create_running_job()
        post_data = self.create_complete_step_result_post_data(result.position)
        # unknown client
        url = self.complete_step_result_url(job, name="unknown_client")
        self.set_counts()
        response = self.client_post_json(url, post_data)
        self.compare_counts()
        self.assertEqual(response.status_code, 400) # bad request

    def test_complete_step_result_bad_client(self):
        job, result = self.create_running_job()
        post_data = self.create_complete_step_result_post_data(result.position)
        # bad client
        client2 = utils.create_client(name='other_client')
        url = self.complete_step_result_url(job, name=client2.name)
        self.set_counts()
        response = self.client_post_json(url, post_data)
        self.compare_counts()
        self.assertEqual(response.status_code, 400) # bad request

    def test_complete_step_result_ok(self):
        job, result = self.create_running_job()
        post_data = self.create_complete_step_result_post_data(result.position)
        # ok
        url = self.complete_step_result_url(job)
        self.set_counts()
        response = self.client_post_json(url, post_data)
        self.compare_counts()
        self.assertEqual(response.status_code, 200)
        result.refresh_from_db()
        self.assertEqual(result.status, models.JobStatus.SUCCESS)
        self.assertEqual(result.job.failed_step, "")

    def test_complete_step_result_intermittent_ok(self):
        job, result = self.create_running_job()
        post_data = self.create_complete_step_result_post_data(result.position)
        url = self.complete_step_result_url(job)
        # step result succeeded but only due to special circumstances (exit code 85)
        post_data['exit_status'] = 85
        url = self.complete_step_result_url(job)
        self.set_counts()
        response = self.client_post_json(url, post_data)
        self.compare_counts()
        self.assertEqual(response.status_code, 200)
        result.refresh_from_db()
        self.assertEqual(result.status, models.JobStatus.INTERMITTENT_FAILURE)
        self.assertEqual(result.job.failed_step, "")

    def test_complete_step_result_failed_abort(self):
        job, result = self.create_running_job()
        post_data = self.create_complete_step_result_post_data(result.position, exit_status=1)
        # step failed and abort_on_failure=True
        post_data['exit_status'] = 1
        url = self.complete_step_result_url(job)
        self.set_counts()
        response = self.client_post_json(url, post_data)
        self.compare_counts()
        self.assertEqual(response.status_code, 200)
        result.refresh_from_db()
        result.job.refresh_from_db()
        self.assertEqual(result.status, models.JobStatus.FAILED)
        self.assertEqual(result.job.failed_step, result.name)

    def test_complete_step_result_failed(self):
        job, result = self.create_running_job()
        post_data = self.create_complete_step_result_post_data(result.position, exit_status=1)
        # step failed and abort_on_failure=False
        result.abort_on_failure = False
        result.name = "newname"
        result.save()
        result.job.failed_step = ""
        result.job.save()
        url = self.complete_step_result_url(job)
        self.set_counts()
        response = self.client_post_json(url, post_data)
        self.compare_counts()
        self.assertEqual(response.status_code, 200)
        result.refresh_from_db()
        result.job.refresh_from_db()
        self.assertEqual(result.status, models.JobStatus.FAILED)
        self.assertEqual(result.job.failed_step, result.name)
        data = response.json()
        self.assertEqual(data["status"], "OK")
        self.assertEqual(data["command"], None)

    def test_complete_step_result_failed_allowed_abort(self):
        job, result = self.create_running_job()
        post_data = self.create_complete_step_result_post_data(result.position, exit_status=1)
        url = self.complete_step_result_url(job)
        # step failed but allowed, abort_on_failure=True
        post_data['exit_status'] = 1
        result.abort_on_failure = True
        result.allowed_to_fail = True
        result.save()
        self.set_counts()
        response = self.client_post_json(url, post_data)
        self.compare_counts()
        self.assertEqual(response.status_code, 200)
        json_data = response.json()
        self.assertFalse(json_data.get('next_step'))
        result.refresh_from_db()
        result.job.refresh_from_db()
        self.assertEqual(result.status, models.JobStatus.FAILED_OK)
        self.assertEqual(result.job.failed_step, result.name)
        # step failed but allowed, abort_on_failure=True

    def test_complete_step_result_failed_allowed(self):
        job, result = self.create_running_job()
        post_data = self.create_complete_step_result_post_data(result.position, exit_status=1)
        url = self.complete_step_result_url(job)
        # step failed but allowed, abort_on_failure=False
        post_data['exit_status'] = 1
        result.abort_on_failure = False
        result.allowed_to_fail = True
        result.save()
        self.set_counts()
        response = self.client_post_json(url, post_data)
        self.compare_counts()
        self.assertEqual(response.status_code, 200)
        json_data = response.json()
        self.assertFalse(json_data.get('next_step'))
        result.refresh_from_db()
        result.job.refresh_from_db()
        self.assertEqual(result.status, models.JobStatus.FAILED_OK)
        self.assertEqual(result.job.failed_step, result.name)

    def test_complete_step_result_bad_output(self):
        job, result = self.create_running_job()
        post_data = self.create_complete_step_result_post_data(result.position, exit_status=1)
        url = self.complete_step_result_url(job)
        with patch.object(models.StepResult, 'save') as mock_save:
            mock_save.side_effect = [Exception("BAM!"), None, None, None]
            self.set_counts()
            response = self.client_post_json(url, post_data)
            self.compare_counts()
            self.assertEqual(response.status_code, 200)

    @patch.object(Permissions, 'is_collaborator')
    def test_update_remote_job_status(self, mock_collab):
        mock_collab.return_value = False
        # bad job
        url = reverse('ci:client:update_remote_job_status', args=[1000])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)

        response = self.client.post(url)
        self.assertEqual(response.status_code, 404)

        j = utils.create_job()
        j.event.comments_url = 'url'
        j.event.save()
        url = reverse('ci:client:update_remote_job_status', args=[j.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "not allowed")

        response = self.client.post(url)
        self.assertEqual(response.status_code, 405)

        mock_collab.return_value = True
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "not allowed")

        response = self.client.post(url)
        self.assertEqual(response.status_code, 302)
