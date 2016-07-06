import os
from mock import patch
from client.JobGetter import JobGetter
from client import settings
import subprocess
import utils
import threading
import time
from ci import views
import LiveClientTester

class Tests(LiveClientTester.LiveClientTester):
  def create_client_and_job(self, name, sleep=1):
    c = utils.create_inl_client()
    os.environ["BUILD_ROOT"] = "/foo/bar"
    c.client_info["single_shot"] = True
    c.client_info["update_step_time"] = 1
    c.client_info["ssl_cert"] = False # not needed but will get another line of coverage
    c.client_info["server"] = self.live_server_url
    job = utils.create_client_job(self.repo_dir, name=name, sleep=sleep)
    settings.SERVERS = [(self.live_server_url, job.event.build_user.build_key, False)]
    settings.CONFIG_MODULES[job.config.name] = ["moose-dev-gcc"]
    c.client_info["servers"] = [self.live_server_url]
    c.client_info["build_configs"] = [job.config.name]
    c.client_info["build_key"] = job.recipe.build_user.build_key
    return c, job

  def test_run_success(self):
    c, job = self.create_client_and_job("RunSuccess", sleep=2)
    self.set_counts()
    c.run(single=True)
    self.compare_counts(num_clients=1, num_events_completed=1, num_jobs_completed=1, active_branches=1)
    utils.check_complete_job(self, job)

  def test_run_graceful(self):
    c, job = self.create_client_and_job("Graceful", sleep=2)
    self.set_counts()
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
    c, job = self.create_client_and_job("Cancel", sleep=4)
    self.set_counts()
    c.client_info["poll"] = 1
    # cancel signal, should stop
    script = "sleep 3 && kill -USR1 %s" % os.getpid()
    proc = subprocess.Popen(script, shell=True, executable="/bin/bash", stdout=subprocess.PIPE)
    c.run()
    proc.wait()
    self.compare_counts(num_clients=1, canceled=1, num_events_completed=1, num_jobs_completed=1, active_branches=1, events_canceled=1)
    self.assertEqual(c.cancel_signal.triggered, True)
    self.assertEqual(c.graceful_signal.triggered, False)
    utils.check_canceled_job(self, job)

  def test_run_job_cancel(self):
    c, job = self.create_client_and_job("JobCancel", sleep=4)
    self.set_counts()
    # cancel response, should cancel the job
    thread = threading.Thread(target=c.run, args=(True,))
    thread.start()
    time.sleep(4)
    job.refresh_from_db()
    views.set_job_canceled(job)
    thread.join()
    self.compare_counts(num_clients=1, canceled=1, num_events_completed=1, num_jobs_completed=1, active_branches=1, events_canceled=1)
    self.assertEqual(c.cancel_signal.triggered, False)
    self.assertEqual(c.graceful_signal.triggered, False)
    utils.check_canceled_job(self, job)

  def test_run_job_invalidated_basic(self):
    c, job = self.create_client_and_job("JobInvalidated", sleep=40)
    # stop response, should stop the job
    self.set_counts()
    thread = threading.Thread(target=c.run, args=(True,))
    thread.start()
    start_time = time.time()
    time.sleep(4)
    job.refresh_from_db()
    views.set_job_invalidated(job, "Test invalidation")
    thread.join()
    end_time = time.time()
    self.assertGreater(15, end_time-start_time)
    self.compare_counts(num_clients=1, invalidated=1, active_branches=1, num_changelog=1)
    utils.check_stopped_job(self, job)

  def test_run_job_invalidated_nested_bash(self):
    c, job = self.create_client_and_job("JobInvalidated", sleep=40)
    job.delete()
    job = utils.create_job_with_nested_bash(self.repo_dir, name="JobWithNestedBash", sleep=40)
    # stop response, should stop the job
    self.set_counts()
    thread = threading.Thread(target=c.run, args=(True,))
    start_time = time.time()
    thread.start()
    time.sleep(4)
    job.refresh_from_db()
    views.set_job_invalidated(job, "Test invalidation")
    thread.join()
    end_time = time.time()
    self.assertGreater(15, end_time-start_time)
    self.compare_counts(num_clients=1, invalidated=1, active_branches=1, num_changelog=1)
    utils.check_stopped_job(self, job)

  @patch.object(JobGetter, 'find_job')
  def test_exception(self, mock_getter):
    # check exception handler
    mock_getter.side_effect = Exception("oh no!")
    c, job = self.create_client_and_job("JobStop", sleep=4)
    self.set_counts()
    c.run(single=True)
    self.compare_counts()

  def test_check_server_no_job(self):
    # check no jobs
    c, job = self.create_client_and_job("JobStop", sleep=4)
    job.complete = True
    job.save()
    self.set_counts()
    c.check_server(settings.SERVERS[0])
    self.compare_counts(num_clients=1)