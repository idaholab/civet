from django.test import TestCase, Client
from django.test.client import RequestFactory
from ci import models, event
from ci.github import api
from mock import patch
from . import utils

class EventTestCase(TestCase):
  fixtures = ['base']

  def setUp(self):
    self.client = Client()
    self.factory = RequestFactory()

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
        'ssh_url',
        models.GitServer.objects.first(),
        )
    num_before = models.Commit.objects.count()
    commit = gitcommit.create()
    num_after = models.Commit.objects.count()
    self.assertEqual(num_before+1, num_after)

    # same commit should return same
    num_before = models.Commit.objects.count()
    new_commit = gitcommit.create()
    num_after = models.Commit.objects.count()
    self.assertEqual(num_before, num_after)
    self.assertEqual(new_commit, commit)

    # set the ssh_url
    commit.ssh_url = ''
    commit.save()
    commit = gitcommit.create()
    self.assertEqual(commit.ssh_url, 'ssh_url')

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

    # result failed, event should failed
    step_result.status = models.JobStatus.FAILED
    step_result.save()
    result = event.event_status(step_result.job.event)
    self.assertEqual(result, models.JobStatus.FAILED)

    # result failed, event be FAILED_OK
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

    # a failed job, but running jobs keep going
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
    self.assertTrue(job2.ready)

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
    step_result.job.recipe.abort_on_failure = False
    step_result.job.recipe.save()
    step_result.status = models.JobStatus.FAILED_OK
    step_result.save()
    status = event.job_status(job)
    self.assertEqual(status, models.JobStatus.FAILED_OK)

    # failed step but step allowed to fail
    step_result.job.recipe.abort_on_failure = True
    step_result.job.recipe.save()
    step_result.abort_on_failure = False
    step_result.save()
    status = event.job_status(job)
    self.assertEqual(status, models.JobStatus.FAILED)

    # failed step but allowed on all levels
    step_result.job.recipe.abort_on_failure = False
    step_result.job.recipe.save()
    step_result.abort_on_failure = False
    step_result.save()
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

  def test_cancel_event(self):
    ev = utils.create_event()
    j1 = utils.create_job(event=ev)
    j2 = utils.create_job(event=ev)
    j3 = utils.create_job(event=ev)
    event.cancel_event(ev)
    j1.refresh_from_db()
    self.assertEqual(j1.status, models.JobStatus.CANCELED)
    self.assertTrue(j1.complete)
    j2.refresh_from_db()
    self.assertEqual(j2.status, models.JobStatus.CANCELED)
    self.assertTrue(j2.complete)
    j3.refresh_from_db()
    self.assertEqual(j3.status, models.JobStatus.CANCELED)
    self.assertTrue(j3.complete)
    ev.refresh_from_db()
    self.assertEqual(ev.status, models.JobStatus.CANCELED)
    self.assertTrue(ev.complete)

  @patch.object(api.GitHubAPI, 'is_collaborator')
  def test_pullrequest(self, mock_is_collaborator):
    user = utils.get_test_user()
    c1 = utils.create_commit(sha='1', user=user)
    c2 = utils.create_commit(sha='2', user=user)
    r1 = utils.create_recipe(user=user, name='recip1', repo=c1.repo())
    r2 = utils.create_recipe(user=user, name='recip2', repo=c1.repo())
    # another recipe but different user, so it should never activate
    r3 = utils.create_recipe(name='recip3', repo=c1.repo())
    c1_data = event.GitCommitData(user.name, c1.repo().name, c1.branch.name, c1.sha, '', c1.server())
    c2_data = event.GitCommitData(user.name, c2.repo().name, c2.branch.name, c2.sha, '', c2.server())
    pr = event.PullRequestEvent()
    pr.pr_number = 1
    pr.action = event.PullRequestEvent.OPENED
    pr.build_user = user
    pr.title = 'PR 1'
    pr.html_url = 'url'
    pr.full_text = ''
    pr.base_commit = c1_data
    pr.head_commit = c2_data
    request = self.factory.get('/')
    # a valid PR, should just create an event
    num_jobs_before = models.Job.objects.count()
    num_ev_before = models.Event.objects.count()
    pr.save(request)
    num_jobs_after = models.Job.objects.count()
    num_ev_after = models.Event.objects.count()
    self.assertEqual(num_ev_before+1, num_ev_after)

    # now try another event on the PR
    # it should cancel previous events and jobs
    old_ev = models.Event.objects.first()
    c2_data.sha = '3'
    pr.head_commit = c2_data
    num_jobs_before = num_jobs_after
    num_ev_before = num_ev_after
    pr.save(request)
    num_jobs_after = models.Job.objects.count()
    num_ev_after = models.Event.objects.count()
    self.assertEqual(num_jobs_before+2, num_jobs_after)
    self.assertEqual(num_ev_before+1, num_ev_after)
    old_ev.refresh_from_db()
    self.assertEqual(old_ev.status, models.JobStatus.CANCELED)
    self.assertTrue(old_ev.complete)
    new_ev = models.Event.objects.first()

    self.assertEqual(new_ev.status, models.JobStatus.NOT_STARTED)
    self.assertFalse(new_ev.complete)
    for j in new_ev.jobs.all():
      self.assertEqual(j.status, models.JobStatus.NOT_STARTED)
      self.assertFalse(j.complete)

    for j in old_ev.jobs.all():
      self.assertEqual(j.status, models.JobStatus.CANCELED)
      self.assertTrue(j.complete)

    new_ev.jobs.all().delete()
    # Try various automatic settings
    r1.automatic = models.Recipe.MANUAL
    r1.save()
    r2.automatic = models.Recipe.AUTO_FOR_AUTHORIZED
    r2.auto_authorized.add(user)
    r2.save()
    r3 = utils.create_recipe(name='recipe3', user=user, repo=c1.repo())
    r3.automatic = models.Recipe.AUTO_FOR_AUTHORIZED
    r3.save()
    mock_is_collaborator.return_value = False
    pr.save(request)
    new_ev = models.Event.objects.first()

    for j in new_ev.jobs.all():
      self.assertEqual(j.status, models.JobStatus.NOT_STARTED)
      if j.recipe == r1:
        self.assertFalse(j.active)
        self.assertFalse(j.ready)
      elif j.recipe == r2:
        self.assertTrue(j.active)
        self.assertTrue(j.ready)
      elif j.recipe == r3:
        self.assertFalse(j.active)
        self.assertFalse(j.ready)
      # set these for the next test
      j.ready = False
      j.complete = True
      j.save()

    # save the same pull request and make sure the jobs haven't changed
    # and no new events were created
    num_events_before = models.Event.objects.count()
    num_jobs_before = models.Job.objects.count()
    num_ready_before = models.Job.objects.filter(ready=True).count()
    pr.save(request)
    num_events_after = models.Event.objects.count()
    num_jobs_after = models.Job.objects.count()
    num_ready_after = models.Job.objects.filter(ready=True).count()
    self.assertEqual(num_events_before, num_events_after)
    self.assertEqual(num_jobs_before, num_jobs_after)
    self.assertEqual(num_ready_before, num_ready_after)
