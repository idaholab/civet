from django.test import Client
from django.test.client import RequestFactory
from ci import models, event
from ci.github import api
from mock import patch
from . import utils
from ci.recipe.tests import utils as recipe_test_utils
# We use the RecipeRepoReader, RecipeWriter from the civet_recipes/pyrecipe
# But we don't use any of the recipes in there.
import sys, os
from django.conf import settings
sys.path.insert(1, os.path.join(settings.RECIPE_BASE_DIR, "pyrecipe"))
import RecipeReader, RecipeWriter

class EventTests(recipe_test_utils.RecipeTestCase):
  fixtures = ['base']

  def setUp(self):
    super(EventTests, self).setUp()
    self.client = Client()
    self.factory = RequestFactory()
    self.set_counts()
    self.create_default_recipes()
    self.compare_counts(recipes=6, deps=2, current=6, sha_changed=True, num_push_recipes=2, num_pr_recipes=2, num_manual_recipes=1, num_pr_alt_recipes=1, users=2, repos=1, branches=1)

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

  @patch.object(api.GitHubAPI, 'is_collaborator')
  def test_pullrequest(self, mock_is_collaborator):
    # the recipes in ci/recipes/tests are on repo idaholab/civet with builduser 'moosebuild'
    mock_is_collaborator.return_value = True
    other_build_user = utils.create_user_with_token(name="bad_build_user")
    c1 = utils.create_commit(sha='1', branch=self.branch, user=self.owner)
    c2 = utils.create_commit(sha='2', branch=self.branch, user=self.owner)

    # Make sure we only get recipes for the correct build user
    # This shouldn't create an event or any jobs.
    c1_data = event.GitCommitData(self.owner.name, c1.repo().name, c1.branch.name, c1.sha, '', c1.server())
    c2_data = event.GitCommitData(self.owner.name, c2.repo().name, c2.branch.name, c2.sha, '', c2.server())
    pr = event.PullRequestEvent()
    pr.pr_number = 1
    pr.action = event.PullRequestEvent.OPENED
    pr.build_user = other_build_user
    pr.title = 'PR 1'
    pr.html_url = 'url'
    pr.full_text = ''
    pr.base_commit = c1_data
    pr.head_commit = c2_data
    request = self.factory.get('/')
    request.session = {} # the default RequestFactory doesn't have a session
    self.set_counts()
    pr.save(request)
    self.compare_counts()

    # a valid PR, should just create an event, a PR, and 2 jobs
    pr.build_user = self.build_user
    self.set_counts()
    pr.save(request)
    self.compare_counts(events=1, jobs=2, ready=1, prs=1, active=2)

    alt_recipe = models.Recipe.objects.filter(cause=models.Recipe.CAUSE_PULL_REQUEST_ALT).first()
    pr_rec = models.PullRequest.objects.first()
    pr_rec.alternate_recipes.add(alt_recipe)
    # now try another event on the PR
    # it should cancel previous events and jobs
    old_ev = models.Event.objects.first()
    c2_data.sha = '3'
    pr.head_commit = c2_data
    self.set_counts()
    pr.save(request)
    self.compare_counts(jobs=3, ready=2, events=1, commits=1, canceled=2, active=3)
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

    # now try another event on the PR but with a new recipe.
    # Should create a new recipe
    reader = RecipeReader.RecipeReader(self.repo_dir, self.recipe_file)
    r = reader.read()
    r["name"] = "Changed Recipe"
    recipe_str = RecipeWriter.write_recipe_to_string(r)
    self.write_to_repo(recipe_str, "recipe.cfg")
    c2_data.sha = '4'
    pr.head_commit = c2_data
    self.set_counts()
    self.load_recipes()
    pr.save(request)
    self.compare_counts(events=1, recipes=1, jobs=3, ready=2, commits=1, sha_changed=True, deps=1, num_pr_recipes=1, canceled=3, active=3)

    # save the same pull request and make sure the jobs haven't changed
    # and no new events were created.
    self.set_counts()
    pr.save(request)
    self.compare_counts()

    # Try saving the same pull request but the recipe repo has changed.
    # This scenario is one where the event already exists but the
    # user might have just changed something cosmetic about the PR.
    # So we don't change the current recipes on the event or the jobs either.
    # But a recipe does get created
    self.create_recipe_in_repo("recipe_all.cfg", "recipe.cfg")
    r["automatic"] = "manual"
    r["pullrequest_dependencies"] = []
    recipe_str = RecipeWriter.write_recipe_to_string(r)
    self.write_to_repo(recipe_str, "recipe.cfg")

    self.set_counts()
    self.load_recipes()
    pr.save(request)
    self.compare_counts(recipes=1, sha_changed=True, num_pr_recipes=1)
    q = models.Recipe.objects.filter(filename=r["filename"], current=True, cause=models.Recipe.CAUSE_PULL_REQUEST)
    self.assertEqual(q.count(), 1)
    self.assertEqual(q.first().jobs.count(), 0)

    # with only one PR active and it is marked as automatic=manual
    # Job should be created but it shouldn't be ready or active
    reader = RecipeReader.RecipeReader(self.repo_dir, self.recipe_pr_file)
    pr_recipe = reader.read()
    pr_recipe["active"] = False
    recipe_str = RecipeWriter.write_recipe_to_string(pr_recipe)
    self.write_to_repo(recipe_str, "dep1.cfg")

    c2_data.sha = '10'
    pr.head_commit = c2_data
    self.set_counts()
    self.load_recipes()
    pr.save(request)
    # we lost a recipe since it isn't active, so one less current
    self.compare_counts(events=1, jobs=2, sha_changed=True, current=-1, commits=1, ready=1, canceled=3, active=1)
    ev = models.Event.objects.order_by('-created').first()
    self.assertEqual(ev.jobs.count(), 2)
    self.assertEqual(ev.jobs.filter(ready=False).count(), 1)
    self.assertEqual(ev.jobs.filter(active=False).count(), 1)

    # Recipe with automatic=authorized
    # Try out the case where the user IS NOT a collaborator
    mock_is_collaborator.return_value = False
    r["automatic"] = "authorized"
    recipe_str = RecipeWriter.write_recipe_to_string(r)
    self.write_to_repo(recipe_str, "recipe.cfg")

    c2_data.sha = '11'
    pr.head_commit = c2_data
    self.set_counts()
    self.load_recipes()
    pr.save(request)
    self.compare_counts(events=1, recipes=1, jobs=2, ready=0, sha_changed=True, commits=1, num_pr_recipes=1, canceled=2)
    ev = models.Event.objects.order_by('-created').first()
    self.assertEqual(ev.jobs.count(), 2)
    self.assertEqual(ev.jobs.filter(ready=False).count(), 2)
    self.assertEqual(ev.jobs.filter(active=False).count(), 2)

    # Recipe with automatic=authorized
    # Try out the case where the user IS a collaborator
    mock_is_collaborator.return_value = True
    c2_data.sha = '12'
    pr.head_commit = c2_data
    self.set_counts()
    self.load_recipes()
    pr.save(request)
    self.compare_counts(events=1, jobs=2, ready=2, commits=1, canceled=2, active=2)
    ev = models.Event.objects.order_by('-created').first()
    self.assertEqual(ev.jobs.count(), 2)
    self.assertEqual(ev.jobs.filter(ready=True).count(), 2)
    self.assertEqual(ev.jobs.filter(active=True).count(), 2)

  def test_push(self):
    # the recipes in ci/recipes/tests are on repo idaholab/civet with builduser 'moosebuild'
    build_user = utils.create_user(name="moosebuild")
    other_build_user = utils.create_user(name="bad_build_user")
    repo_user = utils.create_user(name="idaholab")
    repo = utils.create_repo(name="civet", user=repo_user)
    branch = utils.create_branch(name="devel", user=repo_user, repo=repo)
    c1 = utils.create_commit(sha='1', branch=branch, user=repo_user)
    c2 = utils.create_commit(sha='2', branch=branch, user=repo_user)

    # Make sure if there is a push and there are no recipes, we don't leave anything around
    # This shouldn't create an event or any jobs.
    c1_data = event.GitCommitData("no_exist", "no_exist", "no_exist", "1", "", c1.server())
    c2_data = event.GitCommitData(repo_user.name, c2.repo().name, c2.branch.name, c2.sha, '', c2.server())
    push = event.PushEvent()
    push.build_user = build_user
    push.full_text = ''
    push.base_commit = c1_data
    push.head_commit = c2_data
    request = self.factory.get('/')
    self.set_counts()
    push.save(request)
    self.compare_counts()

    # Make sure we only get recipes for the correct build user
    # This shouldn't create an event or any jobs.
    c1_data = event.GitCommitData(repo_user.name, c1.repo().name, c1.branch.name, c1.sha, '', c1.server())
    push.base_commit = c1_data
    push.build_user = other_build_user
    self.set_counts()
    push.save(request)
    self.compare_counts()

    # a valid Push, should just create an event and 2 jobs.
    # 1 job depends on the other so only 1 job should be ready
    push.build_user = build_user
    self.set_counts()
    push.save(request)
    self.compare_counts(events=1, jobs=2, ready=1, active=2)

    # now try another event on the Push
    # it should just create more jobs
    old_ev = models.Event.objects.first()
    c2_data.sha = '3'
    push.head_commit = c2_data
    self.set_counts()
    push.save(request)
    self.compare_counts(events=1, jobs=2, ready=1, commits=1, active=2)
    old_ev.refresh_from_db()
    self.assertEqual(old_ev.status, models.JobStatus.NOT_STARTED)
    self.assertFalse(old_ev.complete)

    # now try another event on the Push but with a new recipe.
    # Should create a new recipe
    reader = RecipeReader.RecipeReader(self.repo_dir, self.recipe_file)
    r = reader.read()
    r["name"] = "Changed Recipe"
    recipe_str = RecipeWriter.write_recipe_to_string(r)
    self.write_to_repo(recipe_str, "recipe.cfg")
    c2_data.sha = '4'
    push.head_commit = c2_data
    self.set_counts()
    self.load_recipes()
    push.save(request)
    self.compare_counts(events=1, jobs=2, ready=1, commits=1, recipes=1, deps=1, sha_changed=True, num_push_recipes=1, active=2)

    # save the same push and make sure the jobs haven't changed
    # and no new events were created.
    self.set_counts()
    self.load_recipes()
    push.save(request)
    self.compare_counts()

    # Try saving the same push but the recipe repo has changed.
    # This scenario is one where the event already exists but the
    # user might have just changed something cosmetic about the Push.
    # So we don't change the current recipes on the event or the jobs either.
    self.create_recipe_in_repo("recipe_all.cfg", "recipe.cfg")
    r["name"] = "Other name change"
    recipe_str = RecipeWriter.write_recipe_to_string(r)
    self.write_to_repo(recipe_str, "recipe.cfg")

    self.set_counts()
    self.load_recipes()
    push.save(request)
    self.compare_counts(recipes=1, sha_changed=True, deps=1, num_push_recipes=1)

  def test_manual(self):
    # the recipes in ci/recipes/tests are on repo idaholab/civet with builduser 'moosebuild'
    build_user = utils.create_user(name="moosebuild")
    other_build_user = utils.create_user(name="bad_build_user")
    repo_user = utils.create_user(name="idaholab")
    repo = utils.create_repo(name="civet", user=repo_user)
    branch = utils.create_branch(name="devel", user=repo_user, repo=repo)
    other_branch = utils.create_branch(name="foo", user=other_build_user)

    # Make sure if there is a manual event and there are no recipes, we don't leave anything around
    # This shouldn't create an event or any jobs.
    manual = event.ManualEvent(build_user, other_branch, "1")
    request = self.factory.get('/')
    self.set_counts()
    manual.save(request)
    self.compare_counts()

    # Make sure we only get recipes for the correct build user
    # This shouldn't create an event or any jobs.
    manual = event.ManualEvent(other_build_user, branch, "1")
    self.set_counts()
    manual.save(request)
    self.compare_counts()

    # a valid Manual, should just create an event and 1 jobs
    manual = event.ManualEvent(build_user, branch, "1")
    self.set_counts()
    manual.save(request)
    self.compare_counts(events=1, jobs=1, ready=1, commits=1, active=1)

    # now try another event on the Manual
    # it should just create more jobs
    old_ev = models.Event.objects.first()
    manual = event.ManualEvent(build_user, branch, "2")
    self.set_counts()
    manual.save(request)
    self.compare_counts(events=1, jobs=1, ready=1, commits=1, active=1)
    old_ev.refresh_from_db()
    self.assertEqual(old_ev.status, models.JobStatus.NOT_STARTED)
    self.assertFalse(old_ev.complete)

    # now try another event on the Manual but with a new recipe.
    # New recipe gets created but since both the PR and Push
    # recipes don't have jobs, the deps don't change
    reader = RecipeReader.RecipeReader(self.repo_dir, self.recipe_file)
    r = reader.read()
    r["name"] = "Changed Recipe"
    recipe_str = RecipeWriter.write_recipe_to_string(r)
    self.write_to_repo(recipe_str, "recipe.cfg")
    manual = event.ManualEvent(build_user, branch, "3")
    self.set_counts()
    self.load_recipes()
    manual.save(request)
    self.compare_counts(events=1, jobs=1, ready=1, commits=1, recipes=1, sha_changed=True, num_manual_recipes=1, active=1)

    # save the same Manual and make sure the jobs haven't changed
    # and no new events were created.
    self.set_counts()
    self.load_recipes()
    manual.save(request)
    self.compare_counts()

    # Try saving the same Manual but the recipe repo has changed.
    # This scenario is one where the event already exists but the
    # user might have just changed something cosmetic about the Manual.
    # So we don't change the current recipes on the event or the jobs either.
    self.create_recipe_in_repo("recipe_all.cfg", "recipe.cfg")
    r["name"] = "Other name change"
    recipe_str = RecipeWriter.write_recipe_to_string(r)
    self.write_to_repo(recipe_str, "recipe.cfg")

    self.set_counts()
    self.load_recipes()
    manual.save(request)
    self.compare_counts(recipes=1, sha_changed=True, num_manual_recipes=1)
