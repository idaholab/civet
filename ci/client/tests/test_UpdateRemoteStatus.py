import ClientTester
from ci import models
from ci.tests import utils
from ci.client import UpdateRemoteStatus

class Tests(ClientTester.ClientTester):
  def test_step_complete_pr_status(self):
    user = utils.get_test_user()
    job = utils.create_job(user=user)
    job.status = models.JobStatus.CANCELED
    job.save()
    results = utils.create_step_result(job=job)
    results.exit_status = 1
    results.save()
    request = self.factory.get('/')
    # this would normally just update the remote status
    # not something we can check.
    # So just make sure that it doesn't throw
    UpdateRemoteStatus.step_complete_pr_status(request, results, job)

  def test_step_start_pr_status(self):
    user = utils.get_test_user()
    job = utils.create_job(user=user)
    job.status = models.JobStatus.CANCELED
    job.save()
    results = utils.create_step_result(job=job)
    results.exit_status = 1
    results.save()
    request = self.factory.get('/')
    # this would normally just update the remote status
    # not something we can check.
    # So just make sure that it doesn't throw
    UpdateRemoteStatus.step_start_pr_status(request, results, job)
