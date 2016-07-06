from django.test import TestCase, Client
from django.test.client import RequestFactory
from py_w3c.validators.html.validator import HTMLValidator
from django.core.urlresolvers import reverse
import json
import utils
from ci import models

class Tests(TestCase):
  fixtures = ['base']

  def setUp(self):
    self.client = Client()
    self.factory = RequestFactory()
    for i in range(5):
      repo = utils.create_repo(name="repo%s" % i)
      repo.active = True
      repo.status = models.JobStatus.SUCCESS
      repo.save()
      for j in range(2):
        b = utils.create_branch(name="branch%s" % j, repo=repo)
        b.status = models.JobStatus.SUCCESS
        b.save()
      for j in range(3):
        b = repo.branches.first()
        pr = utils.create_pr(title="pr%s" % j, number=j+1, repo=repo)
        pr.closed = False
        pr.status = models.JobStatus.SUCCESS
        pr.save()
        ev = utils.create_event(user=repo.user, branch1=b, branch2=b, commit1="%s" % j)
        ev.pull_request = pr
        ev.save()
        for k in range(3):
          r = utils.create_recipe(name="%s%s" % (repo.name, k), repo=repo, branch=b)
          r.private = False
          r.save()
          job = utils.create_job(recipe=r, event=ev)
          job.status = models.JobStatus.SUCCESS
          job.client = utils.create_client(name="client%s/%s" % (repo.name, k))
          job.save()
          utils.create_step_result(job=job)
    utils.create_osversion()
    utils.create_loadedmodule()

  def check_url(self, url):
    response = self.client.get(url)
    vld = HTMLValidator()
    vld.validate_fragment(response.content)
    print(response.content)
    if vld.errors:
      print("ERRORS: %s" % json.dumps(vld.errors, indent=4))
    if vld.warnings:
      print("WARNINGS: %s" % json.dumps(vld.warnings, indent=4))
    self.assertEqual(vld.errors, [])
    self.assertEqual(vld.warnings, [])

  def test_main(self):
    self.check_url(reverse("ci:main"))

  def test_view_branch(self):
    self.check_url(reverse("ci:view_branch", args=[models.Branch.objects.first().pk]))

  def test_view_repo(self):
    self.check_url(reverse("ci:view_repo", args=[models.Repository.objects.first().pk]))

  def test_view_event(self):
    self.check_url(reverse("ci:view_event", args=[models.Event.objects.first().pk]))

  def test_view_pr(self):
    self.check_url(reverse("ci:view_pr", args=[models.PullRequest.objects.latest().pk]))

  def test_view_job(self):
    self.check_url(reverse("ci:view_job", args=[models.Job.objects.first().pk]))

  def test_view_client(self):
    self.check_url(reverse("ci:view_client", args=[models.Client.objects.first().pk]))

  def test_recipe_events(self):
    self.check_url(reverse("ci:recipe_events", args=[models.Recipe.objects.first().pk]))

  def test_view_profile(self):
    self.check_url(reverse("ci:view_profile", args=[models.Recipe.objects.first().build_user.pk]))

  def test_job_info_search(self):
    self.check_url(reverse("ci:job_info_search", args=[]))

  def test_user_repo_settings(self):
    user = utils.get_test_user()
    utils.simulate_login(self.client.session, user)
    self.check_url(reverse("ci:user_repo_settings"))

  def test_event_list(self):
    self.check_url(reverse("ci:event_list"))

  def test_pullrequest_list(self):
    self.check_url(reverse("ci:pullrequest_list"))

  def test_branch_list(self):
    self.check_url(reverse("ci:branch_list"))

  def test_client_list(self):
    self.check_url(reverse("ci:client_list"))

  def test_scheduled(self):
    self.check_url(reverse("ci:scheduled"))
