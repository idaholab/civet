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
    self.assertEqual(result, models.JobStatus.NOT_STARTED)

    # 1 PASSED, 1 FAILED_OK
    sr1.status = models.JobStatus.FAILED_OK
    sr1.save()
    result = event.job_status(self.job0)
    self.assertEqual(result, models.JobStatus.NOT_STARTED)

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
