from ci import models, event
from ci.github import api
from mock import patch
import DBTester
import utils

class Tests(DBTester.DBTester):
  def setUp(self):
    super(Tests, self).setUp()
    self.create_default_recipes()

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
    # everything exists so no change
    self.set_counts()
    commit2 = gitcommit.create()
    self.compare_counts()
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
    self.set_counts()
    commit = gitcommit.create()
    self.compare_counts(users=1, repos=1, branches=1, commits=1)

    # same commit should return same
    self.set_counts()
    new_commit = gitcommit.create()
    self.compare_counts()
    self.assertEqual(new_commit, commit)

    # set the ssh_url
    commit.ssh_url = ''
    commit.save()
    self.set_counts()
    commit = gitcommit.create()
    self.compare_counts()
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
    step_result.status = models.JobStatus.FAILED_OK
    step_result.save()
    result = event.event_status(step_result.job.event)
    self.assertEqual(result, models.JobStatus.FAILED_OK)

  def test_make_jobs_ready(self):
    step_result = utils.create_step_result()
    job = step_result.job
    job.ready = False
    job.complete = False
    job.save()
    self.set_counts()
    event.make_jobs_ready(job.event)
    job.refresh_from_db()
    self.assertTrue(job.ready)
    self.compare_counts(ready=1)

    # all jobs complete and failed
    step_result.status = models.JobStatus.FAILED
    step_result.save()
    job.complete = True
    job.save()
    self.set_counts()
    event.make_jobs_ready(job.event)
    self.assertTrue(job.event.complete)
    self.compare_counts()

    # a failed job, but running jobs keep going
    recipe = utils.create_recipe(name='anotherRecipe')
    job2 = utils.create_job(event=job.event, recipe=recipe)
    step_result2 = utils.create_step_result(job=job2)
    step_result2.status = models.JobStatus.FAILED
    step_result2.save()
    job2.ready = True
    job2.complete = False
    job2.save()
    self.set_counts()
    event.make_jobs_ready(job.event)
    self.compare_counts()
    job2.refresh_from_db()
    self.assertTrue(job2.ready)

    # has a dependency so can't start
    job.recipe.depends_on.add(job2.recipe)
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
    self.set_counts()
    event.make_jobs_ready(job.event)
    # one of the jobs lost its ready status
    self.compare_counts(ready=-1)
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
    step_result.status = models.JobStatus.FAILED_OK
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

  def create_commit_data(self):
    c1 = utils.create_commit(sha='1', branch=self.branch, user=self.owner)
    c2 = utils.create_commit(sha='2', branch=self.branch, user=self.owner)
    c1_data = event.GitCommitData(self.owner.name, c1.repo().name, c1.branch.name, c1.sha, '', c1.server())
    c2_data = event.GitCommitData(self.owner.name, c2.repo().name, c2.branch.name, c2.sha, '', c2.server())
    return c1, c1_data, c2, c2_data

  def create_pr_data(self):
    c1, c1_data, c2, c2_data = self.create_commit_data()
    pr = event.PullRequestEvent()
    pr.pr_number = 1
    pr.action = event.PullRequestEvent.OPENED
    pr.build_user = self.build_user
    pr.title = 'PR 1'
    pr.html_url = 'url'
    pr.full_text = ''
    pr.base_commit = c1_data
    pr.head_commit = c2_data
    request = self.factory.get('/')
    request.session = {} # the default RequestFactory doesn't have a session
    return c1_data, c2_data, pr, request

  def test_pullrequest_bad_user(self):
    """
    Make sure we only get recipes for the correct build user
    This shouldn't create an event or any jobs.
    """
    c1_data, c2_data, pr, request = self.create_pr_data()
    other_build_user = utils.create_user_with_token(name="bad_build_user")
    pr.build_user = other_build_user
    self.set_counts()
    pr.save(request)
    self.compare_counts()

  def test_pullrequest_valid(self):
    """
    a valid PR, should just create an event, a PR, and 2 jobs
    """
    c1_data, c2_data, pr, request = self.create_pr_data()
    self.set_counts()
    pr.save(request)
    self.compare_counts(events=1, jobs=2, ready=1, prs=1, active=2)

    # save the same pull request and make sure the jobs haven't changed
    # and no new events were created.
    self.set_counts()
    pr.save(request)
    self.compare_counts()

  def test_pullrequest_cancel(self):
    c1_data, c2_data, pr, request = self.create_pr_data()
    self.set_counts()
    pr.save(request)
    self.compare_counts(events=1, jobs=2, ready=1, prs=1, active=2)

    alt_recipe = models.Recipe.objects.filter(cause=models.Recipe.CAUSE_PULL_REQUEST_ALT).first()
    pr_rec = models.PullRequest.objects.first()
    pr_rec.alternate_recipes.add(alt_recipe)
    # now try another event on the PR
    # it should cancel previous events and jobs
    # the alt_recipe job and another pr recipe depend on the same recipe
    # so only one job will be ready
    old_ev = models.Event.objects.first()
    c2_data.sha = '10'
    pr.head_commit = c2_data
    self.set_counts()
    pr.save(request)
    self.compare_counts(jobs=3, ready=1, events=1, commits=1, canceled=2, active=3)
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

    # save the same pull request and make sure the jobs haven't changed
    # and no new events were created.
    self.set_counts()
    pr.save(request)
    self.compare_counts()

  def test_pullrequest_change_recipe(self):
    """
    Try saving the same pull request but the recipe repo has changed.
    This scenario is one where the event already exists but the
    user might have just changed something cosmetic about the PR.
    So we don't change the current recipes on the event or the jobs either.
    But a recipe does get created
    """
    c1_data, c2_data, pr, request = self.create_pr_data()
    c1_data, c2_data, pr, request = self.create_pr_data()
    self.set_counts()
    pr.save(request)
    self.compare_counts(events=1, jobs=2, ready=1, prs=1, active=2)

    new_recipe = utils.create_recipe(name="New recipe", user=self.build_user, repo=self.repo, branch=self.branch, cause=models.Recipe.CAUSE_PULL_REQUEST)
    pr_recipe = models.Recipe.objects.filter(cause=models.Recipe.CAUSE_PULL_REQUEST).latest()
    new_recipe.filename = pr_recipe.filename
    new_recipe.save()
    for dep in pr_recipe.depends_on.all():
      new_recipe.depends_on.add(dep)
    pr_recipe.current = False
    pr_recipe.save()

    self.set_counts()
    pr.save(request)
    self.compare_counts()

  def test_pullrequest_not_active(self):
    """
    with only one PR active and one not active
    """
    c1_data, c2_data, pr, request = self.create_pr_data()
    pr_recipe = models.Recipe.objects.filter(cause=models.Recipe.CAUSE_PULL_REQUEST).last()
    pr_recipe.active = False
    pr_recipe.save()

    self.set_counts()
    pr.save(request)
    self.compare_counts(events=1, jobs=1, ready=1, active=1, prs=1)
    ev = models.Event.objects.order_by('-created').first()
    self.assertEqual(ev.jobs.count(), 1)
    self.assertEqual(ev.jobs.filter(ready=False).count(), 0)
    self.assertEqual(ev.jobs.filter(active=False).count(), 0)

  def test_pullrequest_manual(self):
    """
    one PR marked as manual
    """
    c1_data, c2_data, pr, request = self.create_pr_data()
    pr_recipe = models.Recipe.objects.filter(cause=models.Recipe.CAUSE_PULL_REQUEST).last()
    pr_recipe.automatic = models.Recipe.MANUAL
    pr_recipe.save()

    self.set_counts()
    pr.save(request)
    self.compare_counts(events=1, jobs=2, ready=1, active=1, prs=1)
    ev = models.Event.objects.order_by('-created').first()
    self.assertEqual(ev.jobs.count(), 2)
    self.assertEqual(ev.jobs.filter(ready=False).count(), 1)
    self.assertEqual(ev.jobs.filter(active=False).count(), 1)

  @patch.object(api.GitHubAPI, 'is_collaborator')
  def test_pullrequest_authorized_fail(self, mock_is_collaborator):
    """
    Recipe with automatic=authorized
    Try out the case where the user IS NOT a collaborator
    """
    mock_is_collaborator.return_value = False
    c1_data, c2_data, pr, request = self.create_pr_data()
    pr_recipe = models.Recipe.objects.filter(cause=models.Recipe.CAUSE_PULL_REQUEST).last()
    pr_recipe.automatic = models.Recipe.AUTO_FOR_AUTHORIZED
    pr_recipe.save()

    self.set_counts()
    pr.save(request)
    self.compare_counts(events=1, jobs=2, ready=1, active=1, prs=1)
    ev = models.Event.objects.order_by('-created').first()
    self.assertEqual(ev.jobs.count(), 2)
    self.assertEqual(ev.jobs.filter(ready=False).count(), 1)
    self.assertEqual(ev.jobs.filter(active=False).count(), 1)

  @patch.object(api.GitHubAPI, 'is_collaborator')
  def test_pullrequest_authorized_success(self, mock_is_collaborator):
    """
    Recipe with automatic=authorized
    Try out the case where the user IS a collaborator
    """
    mock_is_collaborator.return_value = True
    c1_data, c2_data, pr, request = self.create_pr_data()
    c1_data, c2_data, pr, request = self.create_pr_data()
    pr_recipe = models.Recipe.objects.filter(cause=models.Recipe.CAUSE_PULL_REQUEST).last()
    pr_recipe.automatic = models.Recipe.AUTO_FOR_AUTHORIZED
    pr_recipe.save()

    self.set_counts()
    pr.save(request)
    # one PR depends on the other so only 1 ready
    self.compare_counts(events=1, jobs=2, ready=1, active=2, prs=1)
    ev = models.Event.objects.order_by('-created').first()
    self.assertEqual(ev.jobs.count(), 2)
    self.assertEqual(ev.jobs.filter(ready=True).count(), 1)
    self.assertEqual(ev.jobs.filter(active=True).count(), 2)

  def create_push_data(self):
    c1, c1_data, c2, c2_data = self.create_commit_data()
    push = event.PushEvent()
    push.build_user = self.build_user
    push.full_text = ''
    push.base_commit = c1_data
    push.head_commit = c2_data
    request = self.factory.get('/')
    request.session = {} # the default RequestFactory doesn't have a session
    return c1_data, c2_data, push, request

  def test_push_no_recipes(self):
    # Make sure if there is a push and there are no recipes, we don't leave anything around
    # This shouldn't create an event or any jobs.
    c1_data, c2_data, push, request = self.create_push_data()
    c1_data = event.GitCommitData("no_exist", "no_exist", "no_exist", "1", "", self.build_user.server)
    push.base_commit = c1_data
    self.set_counts()
    push.save(request)
    self.compare_counts()

  def test_push_bad_user(self):
    other_build_user = utils.create_user(name="bad_build_user")
    # Make sure we only get recipes for the correct build user
    # This shouldn't create an event or any jobs.
    c1_data, c2_data, push, request = self.create_push_data()
    push.build_user = other_build_user
    self.set_counts()
    push.save(request)
    self.compare_counts()

  def test_push_valid(self):
    c1_data, c2_data, push, request = self.create_push_data()
    # a valid Push, should just create an event and 2 jobs.
    # 1 job depends on the other so only 1 job should be ready
    self.set_counts()
    push.save(request)
    self.compare_counts(events=1, jobs=2, ready=1, active=2)

    # save again shouldn't do anything
    self.set_counts()
    push.save(request)
    self.compare_counts()

  def test_push_multiple(self):
    c1_data, c2_data, push, request = self.create_push_data()
    self.set_counts()
    push.save(request)
    self.compare_counts(events=1, jobs=2, ready=1, active=2)
    # now try another event on the Push
    # it should just create more jobs
    old_ev = models.Event.objects.first()
    c2_data.sha = '10'
    push.head_commit = c2_data
    self.set_counts()
    push.save(request)
    self.compare_counts(events=1, jobs=2, ready=1, commits=1, active=2)
    old_ev.refresh_from_db()
    self.assertEqual(old_ev.status, models.JobStatus.NOT_STARTED)
    self.assertFalse(old_ev.complete)

  def test_push_recipe(self):
    c1_data, c2_data, push, request = self.create_push_data()
    self.set_counts()
    push.save(request)
    self.compare_counts(events=1, jobs=2, ready=1, active=2)
    # now try another event on the Push but with a new recipe.
    push_recipe = models.Recipe.objects.filter(cause=models.Recipe.CAUSE_PUSH).latest()
    new_recipe = utils.create_recipe(name="New recipe", user=self.build_user, repo=self.repo, branch=self.branch, cause=models.Recipe.CAUSE_PUSH)
    new_recipe.filename = push_recipe.filename
    new_recipe.save()
    push_recipe.current = False
    push_recipe.save()
    c2_data.sha = '10'
    push.head_commit = c2_data
    self.set_counts()
    push.save(request)
    self.compare_counts(events=1, jobs=2, ready=2, commits=1, active=2)

    # save the same push and make sure the jobs haven't changed
    # and no new events were created.
    self.set_counts()
    push.save(request)
    self.compare_counts()

  def test_push_change_recipe(self):
    c1_data, c2_data, push, request = self.create_push_data()
    self.set_counts()
    push.save(request)
    self.compare_counts(events=1, jobs=2, ready=1, active=2)
    # This scenario is one where the event already exists but the
    # for some reason the same push event gets called and the recipes have changed.
    # Nothing should have changed

    push_recipe = models.Recipe.objects.filter(cause=models.Recipe.CAUSE_PUSH).latest()
    new_recipe = utils.create_recipe(name="New recipe", user=self.build_user, repo=self.repo, branch=self.branch, cause=models.Recipe.CAUSE_PUSH)
    new_recipe.filename = push_recipe.filename
    new_recipe.save()
    push_recipe.current = False
    push_recipe.save()
    self.assertEqual(push_recipe.jobs.count(), 1)

    self.set_counts()
    push.save(request)
    self.compare_counts()
    push_recipe.refresh_from_db()
    new_recipe.refresh_from_db()
    self.assertEqual(push_recipe.jobs.count(), 1)
    self.assertEqual(new_recipe.jobs.count(), 0)

  def create_manual_data(self, branch=None, user=None, latest="1"):
    if branch == None:
      branch = self.branch
    if user == None:
      user = self.build_user
    manual = event.ManualEvent(user, branch, latest)
    request = self.factory.get('/')
    request.session = {} # the default RequestFactory doesn't have a session
    return manual, request

  def test_manual_bad_branch(self):
    other_branch = utils.create_branch(name="foo", user=self.build_user)
    manual, request = self.create_manual_data(branch=other_branch)
    # Make sure if there is a manual event and there are no recipes for the branch
    # we don't leave anything around
    # This shouldn't create an event or any jobs.
    self.set_counts()
    manual.save(request)
    self.compare_counts()

  def test_manual_bad_user(self):
    other_build_user = utils.create_user(name="bad_build_user")
    manual, request = self.create_manual_data(user=other_build_user)
    # Make sure we only get recipes for the correct build user
    # This shouldn't create an event or any jobs.
    self.set_counts()
    manual.save(request)
    self.compare_counts()

  def test_manual_valid(self):
    manual, request = self.create_manual_data()
    # a valid Manual, should just create an event and 1 jobs
    self.set_counts()
    manual.save(request)
    self.compare_counts(events=1, jobs=1, ready=1, commits=1, active=1)

    # saving again shouldn't do anything
    self.set_counts()
    manual.save(request)
    self.compare_counts()

  def test_manual_multiple(self):
    manual, request = self.create_manual_data()
    self.set_counts()
    manual.save(request)
    self.compare_counts(events=1, jobs=1, ready=1, commits=1, active=1)
    # now try another event on the Manual
    # it should just create more jobs
    old_ev = models.Event.objects.first()
    manual, request = self.create_manual_data(latest="10")
    self.set_counts()
    manual.save(request)
    self.compare_counts(events=1, jobs=1, ready=1, commits=1, active=1)
    old_ev.refresh_from_db()
    self.assertEqual(old_ev.status, models.JobStatus.NOT_STARTED)
    self.assertFalse(old_ev.complete)

  def test_manual_recipe(self):
    manual, request = self.create_manual_data()
    self.set_counts()
    manual.save(request)
    self.compare_counts(events=1, jobs=1, ready=1, commits=1, active=1)

    # now try another event on the Manual but with a new recipe.
    manual_recipe = models.Recipe.objects.filter(cause=models.Recipe.CAUSE_MANUAL).latest()
    new_recipe = utils.create_recipe(name="New recipe", user=self.build_user, repo=self.repo, branch=self.branch, cause=models.Recipe.CAUSE_MANUAL)
    new_recipe.filename = manual_recipe.filename
    new_recipe.save()
    manual_recipe.current = False
    manual_recipe.save()

    manual, request = self.create_manual_data(latest="10")
    self.set_counts()
    manual.save(request)
    self.compare_counts(events=1, jobs=1, ready=1, commits=1, active=1)
    self.assertEqual(manual_recipe.jobs.count(), 1)
    self.assertEqual(new_recipe.jobs.count(), 1)

    # save the same Manual and make sure the jobs haven't changed
    # and no new events were created.
    self.set_counts()
    manual.save(request)
    self.compare_counts()

  def test_manual_change_recipe(self):
    manual, request = self.create_manual_data()
    self.set_counts()
    manual.save(request)
    self.compare_counts(events=1, jobs=1, ready=1, commits=1, active=1)
    # This scenario is one where the event already exists but the
    # for some reason the same event gets called and the recipes have changed.
    # Nothing should change
    manual_recipe = models.Recipe.objects.filter(cause=models.Recipe.CAUSE_MANUAL).latest()
    new_recipe = utils.create_recipe(name="New recipe", user=self.build_user, repo=self.repo, branch=self.branch, cause=models.Recipe.CAUSE_MANUAL)
    new_recipe.filename = manual_recipe.filename
    new_recipe.save()
    manual_recipe.current = False
    manual_recipe.save()

    self.set_counts()
    manual.save(request)
    self.compare_counts()
    self.assertEqual(manual_recipe.jobs.count(), 1)
    self.assertEqual(new_recipe.jobs.count(), 0)
