from ci import models, PullRequestEvent, GitCommitData
from ci.github import api
from mock import patch
import DBTester
import utils

class Tests(DBTester.DBTester):
  def setUp(self):
    super(Tests, self).setUp()
    self.create_default_recipes()

  def create_commit_data(self):
    c1 = utils.create_commit(sha='1', branch=self.branch, user=self.owner)
    c2 = utils.create_commit(sha='2', branch=self.branch, user=self.owner)
    c1_data = GitCommitData.GitCommitData(self.owner.name, c1.repo().name, c1.branch.name, c1.sha, '', c1.server())
    c2_data = GitCommitData.GitCommitData(self.owner.name, c2.repo().name, c2.branch.name, c2.sha, '', c2.server())
    return c1, c1_data, c2, c2_data

  def create_pr_data(self):
    c1, c1_data, c2, c2_data = self.create_commit_data()
    pr = PullRequestEvent.PullRequestEvent()
    pr.pr_number = 1
    pr.action = PullRequestEvent.PullRequestEvent.OPENED
    pr.build_user = self.build_user
    pr.title = 'PR 1'
    pr.html_url = 'url'
    pr.full_text = ''
    pr.base_commit = c1_data
    pr.head_commit = c2_data
    request = self.factory.get('/')
    request.session = {} # the default RequestFactory doesn't have a session
    return c1_data, c2_data, pr, request

  def test_bad_user(self):
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

  def test_valid(self):
    """
    a valid PR, should just create an event, a PR, and 2 jobs
    """
    c1_data, c2_data, pr, request = self.create_pr_data()
    self.set_counts()
    pr.save(request)
    self.compare_counts(events=1, jobs=2, ready=1, prs=1, active=2, active_repos=1)

    # save the same pull request and make sure the jobs haven't changed
    # and no new events were created.
    self.set_counts()
    pr.save(request)
    self.compare_counts()

  def test_cancel(self):
    c1_data, c2_data, pr, request = self.create_pr_data()
    self.set_counts()
    pr.save(request)
    self.compare_counts(events=1, jobs=2, ready=1, prs=1, active=2, active_repos=1)

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
    self.compare_counts(jobs=3, ready=1, events=1, commits=1, canceled=2, active=3, events_canceled=1, num_changelog=2)
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

  def test_change_recipe(self):
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
    self.compare_counts(events=1, jobs=2, ready=1, prs=1, active=2, active_repos=1)

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

  def test_not_active(self):
    """
    with only one PR active and one not active
    """
    c1_data, c2_data, pr, request = self.create_pr_data()
    pr_recipe = models.Recipe.objects.filter(cause=models.Recipe.CAUSE_PULL_REQUEST).last()
    pr_recipe.active = False
    pr_recipe.save()

    self.set_counts()
    pr.save(request)
    self.compare_counts(events=1, jobs=1, ready=1, active=1, prs=1, active_repos=1)
    ev = models.Event.objects.order_by('-created').first()
    self.assertEqual(ev.jobs.count(), 1)
    self.assertEqual(ev.jobs.filter(ready=False).count(), 0)
    self.assertEqual(ev.jobs.filter(active=False).count(), 0)

  def test_manual(self):
    """
    one PR marked as manual
    """
    c1_data, c2_data, pr, request = self.create_pr_data()
    pr_recipe = models.Recipe.objects.filter(cause=models.Recipe.CAUSE_PULL_REQUEST).last()
    pr_recipe.automatic = models.Recipe.MANUAL
    pr_recipe.save()

    self.set_counts()
    pr.save(request)
    self.compare_counts(events=1, jobs=2, ready=1, active=1, prs=1, active_repos=1)
    ev = models.Event.objects.order_by('-created').first()
    self.assertEqual(ev.jobs.count(), 2)
    self.assertEqual(ev.jobs.filter(ready=False).count(), 1)
    self.assertEqual(ev.jobs.filter(active=False).count(), 1)

  @patch.object(api.GitHubAPI, 'is_collaborator')
  def test_authorized_fail(self, mock_is_collaborator):
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
    self.compare_counts(events=1, jobs=2, ready=1, active=1, prs=1, active_repos=1)
    ev = models.Event.objects.order_by('-created').first()
    self.assertEqual(ev.jobs.count(), 2)
    self.assertEqual(ev.jobs.filter(ready=False).count(), 1)
    self.assertEqual(ev.jobs.filter(active=False).count(), 1)

  @patch.object(api.GitHubAPI, 'is_collaborator')
  def test_authorized_success(self, mock_is_collaborator):
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
    self.compare_counts(events=1, jobs=2, ready=1, active=2, prs=1, active_repos=1)
    ev = models.Event.objects.order_by('-created').first()
    self.assertEqual(ev.jobs.count(), 2)
    self.assertEqual(ev.jobs.filter(ready=True).count(), 1)
    self.assertEqual(ev.jobs.filter(active=True).count(), 2)
