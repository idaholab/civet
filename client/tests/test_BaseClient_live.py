
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
from client import JobGetter
from django.test import override_settings
from mock import patch
from . import utils
import os, subprocess
import threading
import time
from ci import views
from ci.tests import utils as test_utils
from . import LiveClientTester

@override_settings(INSTALLED_GITSERVERS=[test_utils.github_config()])
class Tests(LiveClientTester.LiveClientTester):
    def create_client_and_job(self, recipe_dir, name, sleep=1):
        c = utils.create_base_client()
        os.environ["BUILD_ROOT"] = "/foo/bar"
        c.client_info["single_shot"] = True
        c.client_info["update_step_time"] = 1
        c.client_info["ssl_cert"] = False # not needed but will get another line of coverage
        c.client_info["server"] = self.live_server_url
        c.client_info["servers"] = [self.live_server_url]
        job = utils.create_client_job(recipe_dir, name=name, sleep=sleep)
        c.client_info["build_configs"] = [job.config.name]
        c.client_info["build_key"] = job.recipe.build_user.build_key
        return c, job

    def test_no_signals(self):
        with test_utils.RecipeDir() as recipe_dir:
            # This is just for coverage. We can't really
            # test this because if we send a signal it will just quit
            import signal
            old_signal = signal.SIGUSR2
            del signal.SIGUSR2
            c, job = self.create_client_and_job(recipe_dir, "No signal", sleep=2)
            signal.SIGUSR2 = old_signal

    def test_run_success(self):
        with test_utils.RecipeDir() as recipe_dir:
            c, job = self.create_client_and_job(recipe_dir, "RunSuccess", sleep=2)
            self.set_counts()
            c.run()
            self.compare_counts(num_clients=1, num_events_completed=1, num_jobs_completed=1, active_branches=1)
            utils.check_complete_job(self, job)

    def test_run_graceful(self):
        with test_utils.RecipeDir() as recipe_dir:
            c, job = self.create_client_and_job(recipe_dir, "Graceful", sleep=2)
            self.set_counts()
            c.client_info["single_shot"] = False
            c.client_info["poll"] = 1
            # graceful signal, should complete
            script = "sleep 3 && kill -USR2 %s" % os.getpid()
            proc = subprocess.Popen(script, shell=True, executable="/bin/bash", stdout=subprocess.PIPE)
            c.run()
            proc.wait()
            self.compare_counts(num_clients=1, num_events_completed=1, num_jobs_completed=1, active_branches=1)
            utils.check_complete_job(self, job)
            self.assertEqual(c.graceful_signal.triggered, True)
            self.assertEqual(c.cancel_signal.triggered, False)

    def test_run_cancel(self):
        with test_utils.RecipeDir() as recipe_dir:
            c, job = self.create_client_and_job(recipe_dir, "Cancel", sleep=4)
            self.set_counts()
            c.client_info["single_shot"] = False
            c.client_info["poll"] = 1
            # cancel signal, should stop
            script = "sleep 3 && kill -USR1 %s" % os.getpid()
            proc = subprocess.Popen(script, shell=True, executable="/bin/bash", stdout=subprocess.PIPE)
            c.run()
            proc.wait()
            self.compare_counts(canceled=1,
                    num_clients=1,
                    num_events_completed=1,
                    num_jobs_completed=1,
                    active_branches=1,
                    events_canceled=1,
                    )
            self.assertEqual(c.cancel_signal.triggered, True)
            self.assertEqual(c.graceful_signal.triggered, False)
            utils.check_canceled_job(self, job)

    def test_run_job_cancel(self):
        with test_utils.RecipeDir() as recipe_dir:
            c, job = self.create_client_and_job(recipe_dir, "JobCancel", sleep=4)
            # cancel response, should cancel the job
            self.set_counts()
            thread = threading.Thread(target=c.run)
            thread.start()
            time.sleep(4)
            job.refresh_from_db()
            views.set_job_canceled(job)
            thread.join()
            self.compare_counts(canceled=1,
                    num_clients=1,
                    num_events_completed=1,
                    num_jobs_completed=1,
                    active_branches=1,
                    events_canceled=1,
                    )
            self.assertEqual(c.cancel_signal.triggered, False)
            self.assertEqual(c.graceful_signal.triggered, False)
            utils.check_canceled_job(self, job)

    def test_run_job_invalidated_basic(self):
        with test_utils.RecipeDir() as recipe_dir:
            c, job = self.create_client_and_job(recipe_dir, "JobInvalidated", sleep=40)
            # stop response, should stop the job
            self.set_counts()
            thread = threading.Thread(target=c.run)
            thread.start()
            start_time = time.time()
            time.sleep(4)
            job.refresh_from_db()
            views.set_job_invalidated(job, "Test invalidation")
            thread.join()
            end_time = time.time()
            self.assertGreater(15, end_time-start_time)
            self.compare_counts(invalidated=1, num_clients=1, num_changelog=1)
            utils.check_stopped_job(self, job)

    def test_run_job_invalidated_nested_bash(self):
        with test_utils.RecipeDir() as recipe_dir:
            c, job = self.create_client_and_job(recipe_dir, "JobInvalidated", sleep=40)
            job.delete()
            job = utils.create_job_with_nested_bash(recipe_dir, name="JobWithNestedBash", sleep=40)
            # stop response, should stop the job
            self.set_counts()
            thread = threading.Thread(target=c.run)
            start_time = time.time()
            thread.start()
            time.sleep(4)
            job.refresh_from_db()
            views.set_job_invalidated(job, "Test invalidation")
            thread.join()
            end_time = time.time()
            self.assertGreater(15, end_time-start_time)
            self.compare_counts(num_clients=1, invalidated=1, num_changelog=1)
            utils.check_stopped_job(self, job)

    @patch.object(JobGetter.JobGetter, 'find_job')
    def test_exception(self, mock_getter):
        with test_utils.RecipeDir() as recipe_dir:
            # check exception handler
            mock_getter.side_effect = Exception("oh no!")
            c, job = self.create_client_and_job(recipe_dir, "JobStop", sleep=4)
            self.set_counts()
            c.run()
            self.compare_counts()

    @patch.object(JobGetter.JobGetter, 'find_job')
    def test_runner_error(self, mock_getter):
        with test_utils.RecipeDir() as recipe_dir:
            mock_getter.return_value = None
            c, job = self.create_client_and_job(recipe_dir, "JobError")
            self.set_counts()
            c.runner_error = True
            c.run()
            self.compare_counts()
