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
    self.compare_counts(canceled=3, events_canceled=1, num_changelog=3)

    for j in jobs:
      j.refresh_from_db()
      self.assertEqual(j.status, models.JobStatus.CANCELED)
      self.assertTrue(j.complete)
