
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
from django.urls import reverse
from django.test import override_settings
from django.conf import settings
import  time
from mock import patch
from ci import models, Permissions
from ci.client import views
from ci.tests import utils
from ci.github.api import GitHubAPI
from ci.client.tests import ClientTester
from django.core.cache import cache

@override_settings(INSTALLED_GITSERVERS=[utils.github_config()])
@override_settings(GET_JOB_UPDATE_INTERVAL=5000)
class Tests(ClientTester.ClientTester):
    def setUp(self):
        super(ClientTester.ClientTester, self).setUp()

        self.poll_time = int(settings.GET_JOB_UPDATE_INTERVAL / 1000 + 2)
        self.client = utils.create_client()
        self.user = utils.get_test_user()
        self.build_keys = [self.user.build_key]
        self.build_configs = ['testBuildConfig']

        self.get_cached_job = lambda: views.get_cached_job(self.client,
                                                           self.build_keys,
                                                           self.build_configs)[0]

        self.cached_jobs_key = 'cached_jobs'
        self.get_cached_jobs = lambda: cache.get(self.cached_jobs_key)

        self.event_counter = 0

    def create_ready_job(self):
        event = utils.create_event(user=self.user, commit1=1234 + self.event_counter)
        self.event_counter += 1
        job = utils.create_job(user=self.user, event=event)
        job.ready = True
        job.active = True
        job.status = models.JobStatus.NOT_STARTED
        job.save()
        return job

    def test_cached(self):
        # Should have no cache at this point
        cached_jobs = self.get_cached_jobs()
        self.assertIsNone(cached_jobs)

        # Nothing available
        self.assertIsNone(self.get_cached_job())
        cached_jobs = self.get_cached_jobs()
        self.assertIsNotNone(cached_jobs)
        cached_jobs_expires = cached_jobs.get('expires')

        # Create a job
        job = self.create_ready_job()

        # Should still be nothing available
        cached_jobs = self.get_cached_jobs()
        self.assertEqual(cached_jobs['expires'], cached_jobs_expires)
        self.assertIsNone(self.get_cached_job())

        # Eventually a job should be available
        for i in range(self.poll_time):
            time.sleep(1)
            get_job = self.get_cached_job()

            if get_job is not None:
                cached_jobs = self.get_cached_jobs()
                self.assertNotEqual(cached_jobs.get('expires'), cached_jobs_expires)
                get_job_again = self.get_cached_job()
                self.assertIsNone(get_job_again)
                break
        self.assertGreater(i, 0)
        self.assertIsNotNone(get_job)
        self.assertEqual(get_job.pk, job.pk)

    def test_job_changed(self):
        def check(before_action, after_action, modify_job=None):
            cached_jobs = views.update_cached_jobs()
            self.assertEqual(len(cached_jobs['jobs']), 0)
            job = self.create_ready_job()
            if modify_job is not None:
                modify_job(job)
            cached_jobs = views.update_cached_jobs()
            self.assertEqual(len(cached_jobs['jobs']), 1)
            self.assertEqual(cached_jobs['jobs'][0]['pk'], job.pk)

            state = {}
            before_action(job, state)
            get_job = self.get_cached_job()
            self.assertIsNone(get_job)
            after_action(job, state)
            get_job = self.get_cached_job()
            self.assertIsNotNone(get_job)
            self.assertEqual(cached_jobs['jobs'][0]['pk'], job.pk)

        def set_running(job, state):
            job.status = models.JobStatus.RUNNING
            job.save()
        def set_not_started(job, state):
            job.status = models.JobStatus.NOT_STARTED
            job.save()
        check(set_running, set_not_started)

        config = utils.create_build_config('foo')
        def change_build_config(job, state):
            state['config'] = job.config
            job.config = config
            job.save()
        def change_back_build_config(job, state):
            job.config = state['config']
            job.save()
        check(change_build_config, change_back_build_config)

        def change_build_key(job, state):
            state['build_key'] = self.user.build_key
            self.user.build_key = '9999'
            self.user.save()
        def change_back_build_key(job, state):
            self.user.build_key = state['build_key']
            self.user.save()
        check(change_build_config, change_back_build_config)

        def set_client(job, state):
            job.client = self.client
            job.save()
        def remove_client(job, state):
            job.client = None
            job.save()
        check(set_client, remove_client)

        def modify_job(job):
            job.client = self.client
            job.save()
        check(remove_client, set_client, modify_job)
