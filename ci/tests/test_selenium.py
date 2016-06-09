import SeleniumTester
import utils
from ci import models
import time
import unittest, sys

@unittest.skipIf(sys.platform != "darwin", "Selenium tests are only active on Mac")
class Tests(SeleniumTester.SeleniumTester):
  @SeleniumTester.test_drivers()
  def test_main_nothing(self):
    self.selenium.get(self.live_server_url)
    self.assertEqual(self.selenium.title, "Civet Home")
    self.wait_for_load()

    # no repos
    with self.assertRaises(Exception):
      self.selenium.find_element_by_name("repo_list")
    # no events either but the table should still be there
    event_rows = self.selenium.find_elements_by_xpath("//table[@id='event_table']/tbody/tr")
    self.assertEqual(len(event_rows), 0)

  def check_js_error(self):
    with self.assertRaises(Exception):
      elem = self.selenium.find_element_by_xpath("//body[@JSError]")
      # this shouldn't happen but if it does we want to see the message
      self.assertEqual(elem, "Shouldn't exist!")
    try:
      log = self.selenium.get_log("browser")
    except:
      return
      for entry in log:
        if entry["source"] == "javascript":
          self.assertEqual("Javascript error:", entry["message"] )

  @SeleniumTester.test_drivers()
  def test_main_repo_update(self):
    repo = utils.create_repo()
    branch = utils.create_branch(repo=repo)
    repo.active = True
    repo.save()
    branch.status = models.JobStatus.RUNNING
    branch.save()
    pr = utils.create_pr(repo=repo)
    self.selenium.get(self.live_server_url)
    self.wait_for_load()
    repo_list = self.selenium.find_elements_by_xpath("//ul[@id='repo_list']/li")
    self.assertEqual(len(repo_list), 1)
    self.selenium.find_elements_by_id("repo_%s" % repo.pk)
    b = self.selenium.find_element_by_id("branch_%s" % branch.pk)
    self.assertEqual(b.get_attribute("class"), "boxed_job_status_%s" % branch.status_slug())
    repo_status = self.selenium.find_elements_by_xpath("//ul[@id='repo_status_%s']/li" % repo.pk )
    self.assertEqual(len(repo_status), 1)
    self.selenium.find_element_by_id("pr_%s" % pr.pk)
    pr_status_elem = self.selenium.find_element_by_id("pr_status_%s" % pr.pk)
    self.assertEqual(pr_status_elem.get_attribute("class"), "boxed_job_status_%s" % pr.status_slug())

    # no events either but the table should still be there
    event_rows = self.selenium.find_elements_by_xpath("//table[@id='event_table']/tbody/tr")
    self.assertEqual(len(event_rows), 0)

    branch.status = models.JobStatus.SUCCESS
    branch.save()
    branch.refresh_from_db()
    pr.status = models.JobStatus.SUCCESS
    pr.save()
    pr.refresh_from_db()
    # now wait for the javascript update
    time.sleep(2)
    self.check_js_error()
    self.assertEqual(b.get_attribute("class"), "boxed_job_status_%s" % branch.status_slug())
    pr_status_elem = self.selenium.find_element_by_id("pr_status_%s" % pr.pk)
    self.assertEqual(pr_status_elem.get_attribute("class"), "boxed_job_status_%s" % pr.status_slug())

  @SeleniumTester.test_drivers()
  def test_main_event_update(self):
    ev = utils.create_event()
    pr = utils.create_pr()
    job = utils.create_job(event=ev)
    ev.pull_request = pr
    ev.save()
    self.selenium.get(self.live_server_url)
    self.wait_for_load()
    # no repos
    with self.assertRaises(Exception):
      self.selenium.find_element_by_id("repo_list")

    event_rows = self.selenium.find_elements_by_xpath("//table[@id='event_table']/tbody/tr")
    self.assertEqual(len(event_rows), 1)
    self.selenium.find_element_by_id("event_%s" % ev.pk)
    ev_status = self.selenium.find_element_by_id("event_status_%s" % ev.pk)
    self.assertEqual(ev_status.get_attribute("class"), "job_status_%s" % ev.status_slug())
    job_elem = self.selenium.find_element_by_id("job_%s" % job.pk)
    self.assertEqual(job_elem.get_attribute("class"), "job_status_%s" % job.status_slug())
    before = job_elem.get_attribute("innerHTML")
    self.assertIn(job.recipe.display_name, before)

    ev.status = models.JobStatus.SUCCESS
    ev.save()
    ev.refresh_from_db()
    job.status = models.JobStatus.SUCCESS
    job.failed_step = "Failed"
    job.invalidated = True
    job.save()
    job.refresh_from_db()
    # now wait for the javascript update
    time.sleep(2)
    self.check_js_error()
    event_rows = self.selenium.find_elements_by_xpath("//table[@id='event_table']/tbody/tr")
    self.assertEqual(len(event_rows), 1)
    self.selenium.find_element_by_id("event_%s" % ev.pk)
    ev_status = self.selenium.find_element_by_id("event_status_%s" % ev.pk)
    self.assertEqual(ev_status.get_attribute("class"), "job_status_%s" % ev.status_slug())
    job_elem = self.selenium.find_element_by_id("job_%s" % job.pk)
    self.assertEqual(job_elem.get_attribute("class"), "job_status_%s" % job.status_slug())
    after = job_elem.get_attribute("innerHTML")
    self.assertNotEqual(before, after)
    self.assertIn(job.recipe.display_name, after)
    self.assertIn("Failed", after)
    self.assertIn("Invalidated", after)
