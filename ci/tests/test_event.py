
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

from ci import models, event
import DBTester
import utils

class Tests(DBTester.DBTester):
  def setUp(self):
    super(Tests, self).setUp()
    self.create_default_recipes()

  def test_job_status(self):
    """
    Job status relies on step_result status
    """
    self.create_jobs()
    self.assertEqual(self.job0.step_results.count(), 1)
    sr0 = self.job0.step_results.all().first()
    sr1 = utils.create_step_result(job=self.job0, name="sr1", position=1)
    sr2 = utils.create_step_result(job=self.job0, name="sr2", position=2)
    sr3 = utils.create_step_result(job=self.job0, name="sr3", position=3)
    self.assertEqual(self.job0.step_results.count(), 4)

    # all are NOT_STARTED
    result = event.job_status(self.job0)
    self.assertEqual(result, models.JobStatus.NOT_STARTED)

    # 1 PASSED
    sr0.status = models.JobStatus.SUCCESS
    sr0.save()
    result = event.job_status(self.job0)
    self.assertEqual(result, models.JobStatus.SUCCESS)

    # 1 PASSED, 1 FAILED_OK
    sr1.status = models.JobStatus.FAILED_OK
    sr1.save()
    result = event.job_status(self.job0)
    self.assertEqual(result, models.JobStatus.FAILED_OK)

    # 1 PASSED, 1 FAILED_OK, 1 CANCELED
    sr2.status = models.JobStatus.CANCELED
    sr2.save()
    result = event.job_status(self.job0)
    self.assertEqual(result, models.JobStatus.CANCELED)

    # 1 PASSED, 1 FAILED_OK, 1 FAILED
    sr2.status = models.JobStatus.FAILED
    sr2.save()
    result = event.job_status(self.job0)
    self.assertEqual(result, models.JobStatus.FAILED)

    # 1 PASSED, 1 FAILED_OK, 1 FAILED, 1 RUNNING
    sr3.status = models.JobStatus.RUNNING
    sr3.save()
    result = event.job_status(self.job0)
    self.assertEqual(result, models.JobStatus.RUNNING)

  def create_jobs(self):
    """
    Create 4 jobs.
    j0 -> j1, j2 -> j3
    """
    r0 = utils.create_recipe(name="r0")
    r1 = utils.create_recipe(name="r1", user=r0.build_user, repo=r0.repository)
    r2 = utils.create_recipe(name="r2", user=r0.build_user, repo=r0.repository)
    r3 = utils.create_recipe(name="r3", user=r0.build_user, repo=r0.repository)
    r1.depends_on.add(r0)
    r2.depends_on.add(r0)
    r3.depends_on.add(r1)
    r3.depends_on.add(r2)
    ev = utils.create_event(user=r0.build_user)
    self.job0 = utils.create_job(recipe=r0, event=ev)
    self.job1 = utils.create_job(recipe=r1, event=ev)
    self.job2 = utils.create_job(recipe=r2, event=ev)
    self.job3 = utils.create_job(recipe=r3, event=ev)
    utils.create_step_result(job=self.job0)
    utils.create_step_result(job=self.job1)
    utils.create_step_result(job=self.job2)
    utils.create_step_result(job=self.job3)

  def job_compare(self, j0_ready=False, j1_ready=False, j2_ready=False, j3_ready=False):
    self.job0.refresh_from_db()
    self.job1.refresh_from_db()
    self.job2.refresh_from_db()
    self.job3.refresh_from_db()
    self.assertEqual(self.job0.ready, j0_ready)
    self.assertEqual(self.job1.ready, j1_ready)
    self.assertEqual(self.job2.ready, j2_ready)
    self.assertEqual(self.job3.ready, j3_ready)

  def test_make_jobs_ready_simple(self):
    # a new set of jobs, only the first one that doesn't have dependencies is ready
    self.create_jobs()
    self.set_counts()
    event.make_jobs_ready(self.job0.event)
    self.compare_counts(ready=1)
    self.job_compare(j0_ready=True)

  def test_make_jobs_ready_done(self):
    # all the jobs are complete
    self.create_jobs()
    for j in models.Job.objects.all():
      j.complete = True
      j.active = True
      j.save()
    self.set_counts()
    event.make_jobs_ready(self.job0.event)
    self.compare_counts(num_events_completed=1)

  def test_make_jobs_ready_first_failed(self):
    # first one failed so jobs that depend on it
    # shouldn't be marked as ready
    self.create_jobs()
    self.job0.status = models.JobStatus.FAILED
    self.job0.complete = True
    self.job0.save()

    self.set_counts()
    event.make_jobs_ready(self.job0.event)
    self.compare_counts()
    self.job_compare()

  def test_make_jobs_ready_first_passed(self):
    # first one passed so jobs that depend on it
    # should be marked as ready
    self.create_jobs()
    self.job0.status = models.JobStatus.FAILED_OK
    self.job0.complete = True
    self.job0.save()

    self.set_counts()
    event.make_jobs_ready(self.job0.event)
    self.compare_counts(ready=2)
    self.job_compare(j1_ready=True, j2_ready=True)

  def test_make_jobs_ready_running(self):
    # a failed job, but running jobs keep going
    self.create_jobs()
    self.job0.status = models.JobStatus.FAILED_OK
    self.job0.complete = True
    self.job0.save()
    self.job1.status = models.JobStatus.FAILED
    self.job1.complete = True
    self.job1.save()

    self.set_counts()
    event.make_jobs_ready(self.job0.event)
    self.compare_counts(ready=1)
    self.job_compare(j2_ready=True)

    # make sure calling it again doesn't change things
    self.set_counts()
    event.make_jobs_ready(self.job0.event)
    self.compare_counts()
    self.job_compare(j2_ready=True)

  def test_make_jobs_ready_last_dep(self):
    # make sure multiple dependencies work
    self.create_jobs()
    self.job0.status = models.JobStatus.FAILED_OK
    self.job0.complete = True
    self.job0.ready = True
    self.job0.save()
    self.job1.status = models.JobStatus.SUCCESS
    self.job1.complete = True
    self.job1.ready = True
    self.job1.save()

    self.set_counts()
    event.make_jobs_ready(self.job0.event)
    self.compare_counts(ready=1)
    self.job_compare(j0_ready=True, j1_ready=True, j2_ready=True)

    self.job2.status = models.JobStatus.SUCCESS
    self.job2.complete = True
    self.job2.save()

    self.set_counts()
    event.make_jobs_ready(self.job0.event)
    self.compare_counts(ready=1)
    self.job_compare(j0_ready=True, j1_ready=True, j2_ready=True, j3_ready=True)

  def test_event_odd_deps(self):
    """
    Had the scenario where we have:
      Precheck -> Test:linux, Test:clang -> Merge
    where Test had 2 build configs.
    But the merge recipe had a depends_on with an outdated
    recipe
    make_jobs_ready started the merge without waiting for the
    two Test jobs to finish
    """
    e = utils.create_event()
    e.cause = models.Event.PUSH
    e.save()

    r0 = utils.create_recipe(name='precheck')
    r1 = utils.create_recipe(name='test')
    r2 = utils.create_recipe(name='merge')
    r3 = utils.create_recipe(name='test')
    # These two need to have the same filename
    r1.filename = "my filename"
    r1.save()
    r3.filename = r1.filename
    r3.save()

    r1.build_configs.add(utils.create_build_config("Otherconfig"))
    utils.create_recipe_dependency(recipe=r1 , depends_on=r0)
    utils.create_recipe_dependency(recipe=r2, depends_on=r3)
    j0 = utils.create_job(recipe=r0, event=e)
    j1a = utils.create_job(recipe=r1, event=e, config=r1.build_configs.first())
    j1b = utils.create_job(recipe=r1, event=e, config=r1.build_configs.last())
    j2 = utils.create_job(recipe=r2, event=e)
    self.set_counts()
    event.make_jobs_ready(e)
    self.compare_counts(ready=1)
    j0.refresh_from_db()
    j1a.refresh_from_db()
    j1b.refresh_from_db()
    j2.refresh_from_db()
    self.assertEqual(j0.ready, True)
    self.assertEqual(j1a.ready, False)
    self.assertEqual(j1b.ready, False)
    self.assertEqual(j2.ready, False)
    j0.complete = True
    j0.status = models.JobStatus.SUCCESS
    j0.save()

    self.set_counts()
    event.make_jobs_ready(e)
    self.compare_counts(ready=2)

    j0.refresh_from_db()
    j1a.refresh_from_db()
    j1b.refresh_from_db()
    j2.refresh_from_db()
    self.assertEqual(j0.ready, True)
    self.assertEqual(j1a.ready, True)
    self.assertEqual(j1b.ready, True)
    self.assertEqual(j2.ready, False)

    j1a.complete = True
    j1a.status = models.JobStatus.SUCCESS
    j1a.save()

    self.set_counts()
    event.make_jobs_ready(e)
    self.compare_counts()

    j1b.complete = True
    j1b.status = models.JobStatus.SUCCESS
    j1b.save()

    self.set_counts()
    event.make_jobs_ready(e)
    self.compare_counts(ready=1)

    j2.refresh_from_db()
    self.assertEqual(j2.ready, True)

  def test_event_status(self):
    self.create_jobs()
    # All jobs are NOT_STARTED
    ev = self.job0.event
    self.assertEqual(ev.jobs.count(), 4)
    status = event.event_status(ev)
    self.assertEqual(status, models.JobStatus.NOT_STARTED)

    # 1 SUCCESS but none of them are ready
    self.job0.status = models.JobStatus.SUCCESS
    self.job0.save()
    status = event.event_status(ev)
    self.assertEqual(status, models.JobStatus.NOT_STARTED)

    # 1 SUCCESS
    self.job0.ready = True
    self.job0.save()
    status = event.event_status(ev)
    self.assertEqual(status, models.JobStatus.SUCCESS)

    # 1 SUCCESS, 1 CANCELED
    self.job1.status = models.JobStatus.CANCELED
    self.job1.ready = True
    self.job1.save()
    status = event.event_status(ev)
    self.assertEqual(status, models.JobStatus.CANCELED)

    # 1 SUCCESS, 1 CANCELED, 1 FAILED_OK
    self.job2.status = models.JobStatus.FAILED_OK
    self.job2.ready = True
    self.job2.save()
    status = event.event_status(ev)
    self.assertEqual(status, models.JobStatus.FAILED_OK)

    # 1 SUCCESS, 1 CANCELED, 1 FAILED_OK, 1 FAILED
    self.job3.status = models.JobStatus.FAILED
    self.job3.ready = True
    self.job3.save()
    status = event.event_status(ev)
    self.assertEqual(status, models.JobStatus.FAILED)

    # 1 SUCCESS, 1 CANCELED, 1 FAILED_OK, 1 RUNNING
    self.job3.status = models.JobStatus.RUNNING
    self.job3.ready = True
    self.job3.save()
    status = event.event_status(ev)
    self.assertEqual(status, models.JobStatus.RUNNING)

  def test_cancel_event(self):
    ev = utils.create_event()
    jobs = []
    for i in range(3):
      r = utils.create_recipe(name="recipe %s" % i, user=ev.build_user)
      j = utils.create_job(recipe=r, event=ev, user=ev.build_user)
      jobs.append(j)
    msg = "Test cancel"
    self.set_counts()
    event.cancel_event(ev, msg)
    self.compare_counts(canceled=3, events_canceled=1, num_changelog=3, num_jobs_completed=3, num_events_completed=1)

    for j in jobs:
      j.refresh_from_db()
      self.assertEqual(j.status, models.JobStatus.CANCELED)
      self.assertTrue(j.complete)

  def test_get_active_labels(self):
    self.set_label_settings()
    all_docs = ["docs/foo", "docs/bar", "docs/foobar"]
    some_docs = all_docs[:] + ["tutorials/foo", "tutorials/bar"]
    matched, match_all = event.get_active_labels(all_docs)
    self.assertEqual(matched, ["DOCUMENTATION"])
    self.assertEqual(match_all, True)

    matched, match_all = event.get_active_labels(some_docs)
    self.assertEqual(matched, ["DOCUMENTATION", "TUTORIAL"])
    self.assertEqual(match_all, False)
