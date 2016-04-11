from client import JobGetter
from ci.tests import utils as ci_tests_utils
from ci import models
import json, os
import LiveClientTester

class Tests(LiveClientTester.LiveClientTester):
  def setUp(self):
    super(Tests, self).setUp()
    self.getter = JobGetter.JobGetter(self.client_info)
    self.job = ci_tests_utils.create_job()
    self.client_info["server"] = self.live_server_url
    self.client_info["build_key"] = self.job.event.build_user.build_key
    self.client_info["build_configs"] = [self.job.config.name]

  def create_job_dict(self, job):
    response = {"config": job.config.name, "id": job.pk, "build_key": "%s" % job.event.build_user.build_key }
    return response

  def claim_job_dict(self, job):
    dirname = os.path.dirname(os.path.realpath(__file__))
    fname = os.path.join(dirname, "claim_response.json")
    with open(fname, "r") as f:
      data = json.load(f)
      data["job_id"] = self.job.pk
      data["job_info"]["job_id"] = self.job.pk
      data["job_info"]["environment"]["job_id"] = self.job.pk
      data["job_info"]["environment"]["recipe_id"] = self.job.recipe.pk
      return data

  def test_get_possible_jobs(self):
    # valid server but no jobs to get
    jobs = self.getter.get_possible_jobs()
    self.assertEqual(jobs, [])

    self.job.ready = True
    self.job.active = True
    self.job.complete = False
    self.job.save()
    # test the non error operation
    self.set_counts()
    jobs = self.getter.get_possible_jobs()
    self.compare_counts()
    response = self.create_job_dict(self.job)
    self.assertEqual(jobs, [response])

    # bad server
    self.client_info["server"] = "dummy_server"
    jobs = self.getter.get_possible_jobs()
    self.assertEqual(jobs, None)

  def test_claim_job(self):
    # no jobs to claim
    ret = self.getter.claim_job([])
    self.assertEqual(ret, None)

    # successfull operation
    self.job.ready = True
    self.job.active = True
    self.job.complete = False
    self.job.save()
    jobs = [self.create_job_dict(self.job)]
    self.set_counts()
    ret = self.getter.claim_job(jobs)
    self.compare_counts(num_clients=1, active_branches=1)
    data = self.claim_job_dict(self.job)
    self.assertEqual(ret, data)

    # bad job
    self.job.status = models.JobStatus.RUNNING
    self.job.save()
    self.set_counts()
    ret = self.getter.claim_job(jobs)
    self.compare_counts()
    self.assertEqual(ret, None)

    # job was set invalidated and to run on same client
    self.job.status = models.JobStatus.NOT_STARTED
    self.job.invalidated = True
    self.job.same_client = True
    self.job.client = ci_tests_utils.create_client(name="another client")
    self.job.save()
    self.set_counts()
    ret = self.getter.claim_job(jobs)
    self.compare_counts()
    self.assertEqual(ret, None)

    # no jobs with matching config
    self.job.invalidated = False
    self.job.client = None
    self.job.config.name = "foobar"
    self.job.config.save()
    self.job.save()

    self.set_counts()
    ret = self.getter.claim_job(jobs)
    self.compare_counts()
    self.assertEqual(ret, None)

    # bad server
    self.client_info["server"] = "dummy_server"
    self.set_counts()
    ret = self.getter.claim_job(jobs)
    self.compare_counts()
    self.assertEqual(ret, None)

  def test_find_job(self):
    # no jobs to claim
    ret = self.getter.find_job()
    self.assertEqual(ret, None)

    # successfull operation
    self.job.ready = True
    self.job.active = True
    self.job.complete = False
    self.job.save()
    self.set_counts()
    ret = self.getter.find_job()
    self.compare_counts(active_branches=1)
    data = self.claim_job_dict(self.job)
    self.assertEqual(ret, data)
