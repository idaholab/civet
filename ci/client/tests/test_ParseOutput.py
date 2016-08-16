import ClientTester
from ci.client import ParseOutput
from ci.tests import utils
from ci import models

class Tests(ClientTester.ClientTester):
  def check_modules(self, job, mods):
    self.assertEqual(len(mods), job.loaded_modules.count())
    for mod in mods:
      self.assertTrue(job.loaded_modules.filter(name=mod).exists())

  def check_output(self, output, os_name, os_version, os_other, mods):
    user = utils.get_test_user()
    job = utils.create_job(user=user)
    step_result = utils.create_step_result(job=job)
    step_result.output = output
    step_result.save()
    client = utils.create_client()
    job.client = client
    job.save()

    ParseOutput.set_job_info(job)
    job.refresh_from_db()
    self.assertEqual(job.operating_system.name, os_name)
    self.assertEqual(job.operating_system.version, os_version)
    self.assertEqual(job.operating_system.other, os_other)
    self.check_modules(job, mods)

  def test_set_job_info_ubuntu(self):
    self.check_output(self.get_file("ubuntu_gcc_output.txt"), "Ubuntu", "14.04", "trusty",
      [ 'moose/.gcc_4.9.1', 'moose/.tbb', 'moose/.mpich-3.1.2_gcc', 'moose/.mpich_petsc-3.6.3-gcc-superlu', 'moose-tools', 'moose/.ccache', 'moose/.vtk-6', 'moose-dev-gcc'])

  def test_set_job_info_suse(self):
    self.check_output(self.get_file("suse_11_gcc_output.txt"), "SUSE LINUX", "11", "n/a",
      [ 'pbs', 'use.moose', 'cppunit/1.12.1-GCC-4.9.2', 'tbb/4.3.0.090', 'moose-dev-gcc', 'GCC/4.9.1' ])

  def test_set_job_info_win(self):
    self.check_output(self.get_file("win_output.txt"), "Microsoft Windows Server 2012 R2 Standard", "6.3.9600 N/A Build 9600", "Member Server", ["None"])

  def test_set_job_info_none(self):
    self.check_output("", "Other", "", "", ["None"])

  def test_set_job_stats(self):
    job = utils.create_job()
    ParseOutput.set_job_stats(job)
    self.assertEqual(models.JobTestStatistics.objects.count(), 0)

    step_result = utils.create_step_result(job=job)
    ParseOutput.set_job_stats(job)
    self.assertEqual(models.JobTestStatistics.objects.count(), 0)

    step_result.output = "foo\n\33[1m\33[32m123 passed\33[0m, \33[1m456 skipped\33[0m, \33[1m0 pending\33[0m, \33[1m789 failed\33[0m"
    step_result.save()
    ParseOutput.set_job_stats(job)
    self.assertEqual(models.JobTestStatistics.objects.count(), 1)
    js = models.JobTestStatistics.objects.first()
    self.assertEqual(js.passed, 123)
    self.assertEqual(js.skipped, 456)
    self.assertEqual(js.failed, 789)
