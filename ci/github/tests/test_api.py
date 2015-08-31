from django.test import TestCase, Client
from django.core.urlresolvers import reverse
from ci import models
from ci.tests import utils
import os

class APITestCase(TestCase):
  fixtures = ['base.json',]

  def setUp(self):
    self.client = Client()


  def get_json_file(self, filename):
    dirname, fname = os.path.split(os.path.abspath(__file__))
    with open(dirname + '/' + filename, 'r') as f:
      js = f.read()
      return js

  def test_webhook_pr(self):
    """
    pr_open_01: testmb01 opens pull request from testmb01/repo01:devel to testmb/repo01:devel
    """
    test_user = utils.get_test_user()
    owner = utils.get_owner()
    jobs_before = models.Job.objects.filter(ready=True).count()
    events_before = models.Event.objects.count()

    t1 = self.get_json_file('pr_open_01.json')
    response = self.client.post(reverse('ci:github:webhook', args=[test_user.build_key]), data=t1, content_type="application/json")
    self.assertEqual(response.content, "OK")

    # no recipes are there so no events/jobs should be created
    jobs_after = models.Job.objects.filter(ready=True).count()
    events_after = models.Event.objects.count()
    self.assertEqual(events_after, events_before)
    self.assertEqual(jobs_after, jobs_before)

    repo = utils.create_repo(name='repo01', user=owner)
    utils.create_recipe(user=test_user, repo=repo) # just create it so a job will get created

    response = self.client.post(reverse('ci:github:webhook', args=[test_user.build_key]), data=t1, content_type="application/json")
    self.assertEqual(response.content, "OK")

    jobs_after = models.Job.objects.filter(ready=True).count()
    events_after = models.Event.objects.count()
    self.assertGreater(events_after, events_before)
    self.assertGreater(jobs_after, jobs_before)

  def test_webhook_push(self):
    """
    pr_push_01.json: testmb01 push from testmb01/repo02:devel to testmb/repo02:devel
    """
    test_user = utils.get_test_user()
    owner = utils.get_owner()
    jobs_before = models.Job.objects.filter(ready=True).count()
    events_before = models.Event.objects.count()

    t1 = self.get_json_file('push_01.json')
    response = self.client.post(reverse('ci:github:webhook', args=[test_user.build_key]), data=t1, content_type="application/json")
    self.assertEqual(response.content, "OK")

    # no recipes are there so no events/jobs should be created
    jobs_after = models.Job.objects.filter(ready=True).count()
    events_after = models.Event.objects.count()
    self.assertEqual(events_after, events_before)
    self.assertEqual(jobs_after, jobs_before)

    repo = utils.create_repo(name='repo02', user=owner)
    branch = utils.create_branch(name='devel', repo=repo)
    utils.create_recipe(user=test_user, repo=repo, branch=branch, cause=models.Recipe.CAUSE_PUSH) # just create it so a job will get created

    response = self.client.post(reverse('ci:github:webhook', args=[test_user.build_key]), data=t1, content_type="application/json")
    self.assertEqual(response.content, "OK")

    jobs_after = models.Job.objects.filter(ready=True).count()
    events_after = models.Event.objects.count()
    self.assertGreater(events_after, events_before)
    self.assertGreater(jobs_after, jobs_before)
