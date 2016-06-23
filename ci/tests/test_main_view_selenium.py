import SeleniumTester
import utils
from ci import models
from django.core.urlresolvers import reverse
from django.test import override_settings

class Tests(SeleniumTester.SeleniumTester):
  @SeleniumTester.test_drivers()
  def test_nothing(self):
    self.get()
    self.assertEqual(self.selenium.title, "Civet Home")
    self.check_repos()
    self.check_events()

  @SeleniumTester.test_drivers()
  def test_repo_update_all(self):
    repo, branch = self.create_repo_with_prs()
    self.get()
    self.check_repos()
    self.check_events()
    self.wait_for_js()

    branch.status = models.JobStatus.SUCCESS
    branch.save()
    for pr in repo.pull_requests.all():
      pr.status = models.JobStatus.SUCCESS
      pr.title = "New title"
      pr.username = "foobar"
      pr.save()
    self.wait_for_js()
    self.check_js_error()
    self.check_repos()
    self.check_events()

  @SeleniumTester.test_drivers()
  def test_repo_update_branch(self):
    repo, branch = self.create_repo_with_prs()
    self.get()
    self.check_repos()
    self.check_events()
    # need to sleep so that last_modified will trigger
    self.wait_for_js()

    branch.status = models.JobStatus.SUCCESS
    branch.save()
    self.wait_for_js()
    self.check_js_error()
    self.check_repos()
    self.check_events()

  @SeleniumTester.test_drivers()
  def test_repo_update_pr(self):
    repo, branch = self.create_repo_with_prs()
    self.get()
    self.check_repos()
    self.check_events()
    self.wait_for_js()

    pr = repo.pull_requests.last()
    pr.status = models.JobStatus.SUCCESS
    pr.title = "New title"
    pr.username = "foobar"
    pr.save()
    self.wait_for_js()
    self.check_js_error()
    self.check_repos()
    self.check_events()

  @SeleniumTester.test_drivers()
  def test_new_repo(self):
    repo, branch = self.create_repo_with_prs()
    self.get()
    self.check_repos()
    self.check_events()
    self.wait_for_js()
    repo2, branch2 = self.create_repo_with_prs(name="repo2")
    self.wait_for_js()
    self.check_js_error()
    self.check_repos()
    self.check_events()

  @SeleniumTester.test_drivers()
  def test_new_branch(self):
    repo, branch = self.create_repo_with_prs()
    self.get()
    self.check_repos()
    self.check_events()
    self.wait_for_js()

    branch2 = utils.create_branch(name="branch2", repo=repo)
    branch2.status = models.JobStatus.SUCCESS
    branch2.save()
    self.wait_for_js()
    self.check_js_error()
    self.check_repos()
    self.check_events()

  @SeleniumTester.test_drivers()
  def test_new_pr(self):
    repo, branch = self.create_repo_with_prs()
    self.get()
    self.check_repos()
    self.check_events()

    pr = utils.create_pr(repo=repo, number=200)
    pr.status = models.JobStatus.RUNNING
    pr.save()
    self.wait_for_js()
    self.check_js_error()
    self.check_repos()
    self.check_events()

  @SeleniumTester.test_drivers()
  def test_close_pr(self):
    repo, branch = self.create_repo_with_prs()
    self.get()
    self.check_repos()
    self.check_events()

    pr = repo.pull_requests.first()
    pr.closed = True
    pr.save()
    self.wait_for_js()
    self.check_js_error()
    self.check_repos()
    self.check_events()

  @SeleniumTester.test_drivers()
  def test_event_update(self):
    ev = self.create_event_with_jobs()
    self.get()
    self.check_repos()
    self.check_events()

    ev.status = models.JobStatus.SUCCESS
    ev.save()
    for job in ev.jobs.all():
      job.status = models.JobStatus.SUCCESS
      job.failed_step = "Failed"
      job.invalidated = True
      job.save()
    self.wait_for_js()
    self.check_js_error()
    self.check_repos()
    self.check_events()

  @SeleniumTester.test_drivers()
  def test_new_event(self):
    self.create_event_with_jobs()
    self.get()
    self.check_repos()
    self.check_events()

    # wait again to make sure new event has different timestamp
    self.wait_for_js()
    self.create_event_with_jobs(commit='4321')
    self.wait_for_js()
    self.check_js_error()
    self.check_repos()
    self.check_events()

  @SeleniumTester.test_drivers()
  def test_event_new_job(self):
    self.create_event_with_jobs()
    self.get()
    self.check_repos()
    self.check_events()

    ev = models.Event.objects.first()
    r2 = utils.create_recipe(name="r2")
    ev.save() # to trigger the update
    utils.create_job(event=ev, recipe=r2)
    self.wait_for_js()
    self.check_js_error()
    self.check_repos()
    self.check_events()

  @SeleniumTester.test_drivers()
  @override_settings(DEBUG=True)
  def test_repo_preferences(self):
    repos = []
    for i in range(3):
      repo, branch = self.create_repo_with_prs(name="repo%s" % i)
      self.create_event_with_jobs(user=repo.user, branch1=branch, branch2=branch)
      repos.append(repo)
      self.wait_for_js(wait=1)
    # user not logged in
    self.get()
    self.check_repos()
    self.check_events()

    user = repos[0].user
    start_session_url = reverse('ci:start_session', args=[user.pk])
    self.get(start_session_url)
    self.wait_for_js()

    # user logged in, no repo prefs
    self.get()
    self.check_repos()
    self.check_events()

    for i in range(3):
      user.preferred_repos.add(repos[i])
      self.get()
      if i == (len(repos)-1):
        self.check_repos()
        self.check_events()
      else:
        repo_list = self.selenium.find_elements_by_xpath("//ul[@id='repo_status']/li")
        self.assertEqual(len(repo_list), user.preferred_repos.count())
        with self.assertRaises(Exception):
          self.check_repos()
        with self.assertRaises(Exception):
          self.check_events()
        events = []
        for repo in user.preferred_repos.all():
          self.check_repo_status(repo)
          for ev in models.Event.objects.filter(base__branch__repository=repo).all():
            self.check_event_row(ev)
            events.append(ev)
        event_rows = self.selenium.find_elements_by_xpath("//table[@id='event_table']/tbody/tr")
        self.assertEqual(len(event_rows), len(events))
        self.get("/?default")
        self.check_repos()
        self.check_events()
