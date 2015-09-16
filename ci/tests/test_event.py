from django.test import TestCase, Client
from ci import models, event
from . import utils

class EventTestCase(TestCase):
  fixtures = ['base']

  def setUp(self):
    self.client = Client()

  def test_gitcommitdata(self):
    commit = utils.create_commit()
    gitcommit = event.GitCommitData(
        commit.user().name,
        commit.repo().name,
        commit.branch.name,
        commit.sha,
        commit.ssh_url,
        commit.server(),
        )
    commit2 = gitcommit.create()
    self.assertEqual(commit, commit2)

    # new commit
    gitcommit = event.GitCommitData(
        'no_exist',
        'no_exist',
        'no_exist',
        '1234',
        '',
        models.GitServer.objects.first(),
        )
    num_before = models.Commit.objects.count()
    commit = gitcommit.create()
    num_after = models.Commit.objects.count()
    self.assertEqual(num_before+1, num_after)

  def test_status(self):
    status = set([models.JobStatus.FAILED, models.JobStatus.SUCCESS])
    result = event.get_status(status)
    self.assertEqual(result, models.JobStatus.FAILED)

    status = set([models.JobStatus.CANCELED, models.JobStatus.SUCCESS])
    result = event.get_status(status)
    self.assertEqual(result, models.JobStatus.CANCELED)

    status = set([models.JobStatus.CANCELED, models.JobStatus.SUCCESS, models.JobStatus.FAILED])
    result = event.get_status(status)
    self.assertEqual(result, models.JobStatus.FAILED)

    status = set([models.JobStatus.SUCCESS, models.JobStatus.FAILED_OK])
    result = event.get_status(status)
    self.assertEqual(result, models.JobStatus.FAILED_OK)

    status = set([models.JobStatus.SUCCESS, models.JobStatus.RUNNING])
    result = event.get_status(status)
    self.assertEqual(result, models.JobStatus.RUNNING)

    step_result = utils.create_step_result()
    result = event.job_status(step_result.job)
    self.assertEqual(result, models.JobStatus.NOT_STARTED)

    result = event.event_status(step_result.job.event)
    self.assertEqual(result, models.JobStatus.NOT_STARTED)

    step_result.status = models.JobStatus.FAILED
    step_result.save()
    result = event.event_status(step_result.job.event)
    self.assertEqual(result, models.JobStatus.FAILED)

    step_result.job.recipe.abort_on_failure = False
    step_result.job.recipe.save()
    result = event.event_status(step_result.job.event)
    self.assertEqual(result, models.JobStatus.FAILED_OK)

  def test_make_jobs_ready(self):
    step_result = utils.create_step_result()
    job = step_result.job
    job.ready = False
    job.complete = False
    job.save()
    event.make_jobs_ready(job.event)
    job.refresh_from_db()
    self.assertTrue(job.ready)

    # all jobs complete and failed
    step_result.status = models.JobStatus.FAILED
    step_result.save()
    job.complete = True
    job.save()
    event.make_jobs_ready(job.event)
    self.assertTrue(job.event.complete)

    # a failed job, so don't continue
    recipe = utils.create_recipe(name='anotherRecipe')
    job2 = utils.create_job(event=job.event, recipe=recipe)
    step_result2 = utils.create_step_result(job=job2)
    step_result2.status = models.JobStatus.FAILED
    step_result2.save()
    job2.ready = True
    job2.complete = False
    job2.save()
    event.make_jobs_ready(job.event)
    job2.refresh_from_db()
    self.assertFalse(job2.ready)

    # has a dependency so can't start
    models.RecipeDependency.objects.create(recipe=job.recipe, dependency=job2.recipe)
    step_result.status = models.JobStatus.NOT_STARTED
    step_result.save()
    step_result2.status = models.JobStatus.NOT_STARTED
    step_result2.save()
    job.ready = True
    job.active = True
    job.complete = False
    job.save()
    job2.complete = False
    job2.active = True
    job2.ready = True
    job2.save()
    event.make_jobs_ready(job.event)
    job.refresh_from_db()
    self.assertFalse(job.ready)
    job2.refresh_from_db()
    self.assertTrue(job2.ready)

  def test_job_status(self):
    step_result = utils.create_step_result()
    step_result.status = models.JobStatus.SUCCESS
    step_result.save()
    job = step_result.job

    # everything good
    status = event.job_status(job)
    self.assertEqual(status, models.JobStatus.SUCCESS)

    # failed step
    step_result.status = models.JobStatus.FAILED
    step_result.save()
    status = event.job_status(job)
    self.assertEqual(status, models.JobStatus.FAILED)

    # failed step but allowed
    step_result.step.recipe.abort_on_failure = False
    step_result.step.recipe.save()
    status = event.job_status(job)
    self.assertEqual(status, models.JobStatus.FAILED_OK)

    # failed step but step allowed to fail
    step_result.step.recipe.abort_on_failure = True
    step_result.step.recipe.save()
    step_result.step.abort_on_failure = False
    step_result.step.save()
    status = event.job_status(job)
    self.assertEqual(status, models.JobStatus.FAILED)

    # failed step but allowed on all levels
    step_result.step.recipe.abort_on_failure = False
    step_result.step.recipe.save()
    step_result.step.abort_on_failure = False
    step_result.step.save()
    status = event.job_status(job)
    self.assertEqual(status, models.JobStatus.FAILED_OK)

    # running step
    step_result.status = models.JobStatus.RUNNING
    step_result.save()
    status = event.job_status(job)
    self.assertEqual(status, models.JobStatus.RUNNING)

    # canceled step
    step_result.status = models.JobStatus.CANCELED
    step_result.save()
    status = event.job_status(job)
    self.assertEqual(status, models.JobStatus.CANCELED)
