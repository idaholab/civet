from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from selenium import webdriver
import functools
from selenium.webdriver.support.wait import WebDriverWait
from django.conf import settings
from ci import models
from ci.tests import utils
import unittest, sys
import time

# This decorator was found at
# https://groups.google.com/forum/#!msg/django-users/Sckf9y2xIho/mwLTr8YyNDkJ
# and allows for running multiple browsers

def test_drivers(pool_name='drivers', target_attr='selenium'):
    """
    Run tests with `target_attr` set to each instance in the `WebDriverPool`
    named `pool_name`.

    For example, in you setUpClass method of your LiveServerTestCase:

        # Importing the necessaries:
        from selenium import webdriver

        ### In your TestCase:

        # Be sure to add a place holder attribute for the driver variable
        selenium = None

        # Set up drivers
        @classmethod
        def setUpClass(cls):
            cls.drivers = WebDriverList(
                webdriver.Chrome(),
                webdriver.Firefox(),
                webdriver.Opera(),
                webdriver.PhantomJS,
            )
            super(MySeleniumTests, cls).setUpClass()

        # Tear down drivers
        @classmethod
        def tearDownClass(cls):
            cls.drivers.quit()
            super(MySeleniumTests, cls).tearDownClass()

        # Use drivers
        @test_drivers()
        def test_login(self):
            self.selenium.get('%s%s' % (self.live_server_url, '/'))
            self.assertEquals(self.selenium.title, 'Awesome Site')

    This will run `test_login` with each of the specified drivers as the
    attribute named "selenium"

    """
    def wrapped(test_func):
        @functools.wraps(test_func)
        def decorated(test_case, *args, **kwargs):
            test_class = test_case.__class__
            web_driver_pool = getattr(test_class, pool_name)
            for web_driver in web_driver_pool:
                setattr(test_case, target_attr, web_driver)
                test_func(test_case, *args, **kwargs)
        return decorated
    return wrapped

class WebDriverList(list):
    """
    A sequence that has a `.quit` method that will run on each item in the list.
    Used to easily "quit" a list of WebDrivers.
    """

    def __init__(self, *drivers):
        super(WebDriverList, self).__init__(drivers)

    def quit(self):
        for driver in self:
            driver.quit()

@unittest.skipIf(sys.platform != "darwin", "Selenium tests are only active on Mac")
class SeleniumTester(StaticLiveServerTestCase):
  fixtures = ['base.json']
  selenium = None

  @classmethod
  def setUpClass(cls):
    cls.drivers = WebDriverList(
#        cls.create_chrome_driver(),
        cls.create_firefox_driver(),
    )
    super(SeleniumTester, cls).setUpClass()
    #cls.selenium = cls.create_firefox_driver()
    #cls.selenium.implicitly_wait(2)
    #cls.selenium = cls.create_chrome_driver()

  @classmethod
  def tearDownClass(cls):
    cls.drivers.quit()
    #cls.selenium.quit()
    super(SeleniumTester, cls).tearDownClass()

  @classmethod
  def create_chrome_driver(cls):
    """
    Get the chromedriver from:
    https://sites.google.com/a/chromium.org/chromedriver/
    and put it your path
    """
    driver = webdriver.Chrome()
    driver.implicitly_wait(2)
    return driver

  @classmethod
  def create_firefox_driver(cls):
    """
    Instructions to get this working:
    https://developer.mozilla.org/en-US/docs/Mozilla/QA/Marionette/WebDriver
    Driver can be found here: https://github.com/mozilla/geckodriver/releases
    Important: After downloading the driver, rename it to 'wires' and put it in your path and chmod 755
    """
    from selenium.webdriver.common.desired_capabilities import DesiredCapabilities
    cap = DesiredCapabilities.FIREFOX
    cap['marionette'] = True
    driver = webdriver.Firefox(capabilities=cap)
    driver.implicitly_wait(2)
    return driver

  def clear_db(self):
    for o in models.Recipe.objects.all():
      o.delete()
    for o in models.GitServer.objects.all():
      o.delete()
    for o in models.Repository.objects.all():
      o.delete()

  def setUp(self):
    super(SeleniumTester, self).setUp()
#    self.selenium = self.create_firefox_driver()
    self.orig_home_interval = settings.HOME_PAGE_UPDATE_INTERVAL
    self.orig_job_interval = settings.JOB_PAGE_UPDATE_INTERVAL
    self.orig_event_interval = settings.EVENT_PAGE_UPDATE_INTERVAL
    settings.HOME_PAGE_UPDATE_INTERVAL = 1000
    settings.JOB_PAGE_UPDATE_INTERVAL = 1000
    settings.EVENT_PAGE_UPDATE_INTERVAL = 1000

  def tearDown(self):
#    self.selenium.quit()
    super(SeleniumTester, self).tearDown()
    settings.HOME_PAGE_UPDATE_INTERVAL = self.orig_home_interval
    settings.JOB_PAGE_UPDATE_INTERVAL = self.orig_job_interval
    settings.EVENT_PAGE_UPDATE_INTERVAL = self.orig_event_interval

  def get(self, url="", wait_time=2):
    full_url = "%s%s" % (self.live_server_url, url)
    self.selenium.get(full_url)
    self.wait_for_load(timeout=wait_time)
    WebDriverWait(self.selenium, wait_time).until(lambda driver: driver.find_element_by_tag_name('body'))

  def wait_for_load(self, timeout=2):
    WebDriverWait(self.selenium, timeout).until(lambda driver: driver.find_element_by_tag_name('body'))

  def wait_for_js(self, wait=2):
    time.sleep(wait)

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

  def check_repos(self):
    active_repos = models.Repository.objects.filter(active=True)
    repo_list = self.selenium.find_elements_by_xpath("//ul[@id='repo_status']/li")
    self.assertEqual(len(repo_list), active_repos.count())
    for repo in active_repos.all():
      self.check_repo_status(repo)

  def check_repo_status(self, repo):
    repo_elem = self.selenium.find_element_by_id("repo_%s" % repo.pk)
    repo_html = repo_elem.get_attribute('innerHTML')
    self.assertIn(repo.name, repo_html)
    branches = repo.branches.exclude(status=models.JobStatus.NOT_STARTED)
    for branch in branches.all():
      self.check_class("branch_%s" % branch.pk, "boxed_job_status_%s" % branch.status_slug())

    prs = repo.pull_requests.filter(closed=False)
    for pr in prs.all():
      self.check_class("pr_status_%s" % pr.pk, "boxed_job_status_%s" % pr.status_slug())
      pr_elem = self.selenium.find_element_by_id("pr_%s" % pr.pk)
      pr_html = pr_elem.get_attribute('innerHTML')
      self.assertIn(pr.title, pr_html)
      self.assertIn(str(pr.number), pr_html)
      self.assertIn(pr.username, pr_html)
      # TODO: Make sure PRs are sorted

  def check_event_row(self, ev):
    event_tds = self.selenium.find_elements_by_xpath("//tr[@id='event_%s']/td" % ev.pk)
    sorted_jobs = ev.get_sorted_jobs()
    if sorted_jobs:
      num_boxes = len(sorted_jobs) - 1 # each group will have a continuation box, except the last
      for group in sorted_jobs:
        num_boxes += len(group)
      num_boxes += 1 # this is the event description
      self.assertEqual(len(event_tds), num_boxes)

    depends = self.selenium.find_elements_by_xpath('//td[@class="depends"]')
    for dep in depends:
      dep_html = dep.get_attribute('innerHTML')
      self.assertEqual(dep_html, '<span class="glyphicon glyphicon-arrow-right"></span>')

    self.selenium.find_element_by_id("event_%s" % ev.pk)
    ev_status = self.check_class("event_status_%s" % ev.pk, "job_status_%s" % ev.status_slug())
    ev_html = ev_status.get_attribute('innerHTML')
    self.assertIn(str(ev.base.branch.repository.name), ev_html)
    if ev.pull_request:
      self.assertIn(str(ev.pull_request), ev_html)
    else:
      self.assertIn(str(ev.cause_str), ev_html)

    for job in ev.jobs.all():
      job_elem = self.check_class("job_%s" % job.pk, "job_status_%s" % job.status_slug())
      html = job_elem.get_attribute("innerHTML")
      self.assertIn(job.recipe.display_name, html)

      if job.invalidated:
        self.assertIn("Invalidated", html)
      else:
        self.assertNotIn("Invalidated", html)

      if job.failed_step:
        self.assertIn(job.failed_step, html)

  def check_events(self):
    events = models.Event.objects
    event_rows = self.selenium.find_elements_by_xpath("//table[@id='event_table']/tbody/tr")
    self.assertEqual(len(event_rows), events.count())
    for ev in events.all():
      self.check_event_row(ev)
    # TODO: Make sure events are sorted

  def create_repo_with_prs(self, name="Repo0"):
    repo = utils.create_repo(name=name)
    branch = utils.create_branch(name="branch1", repo=repo)
    repo.active = True
    repo.save()
    branch.status = models.JobStatus.RUNNING
    branch.save()
    for i in range(3):
      pr = utils.create_pr(repo=repo, number=i+1)
      pr.status = models.JobStatus.RUNNING
      pr.save()
    return repo, branch

  def check_pr(self, pr):
    pr.refresh_from_db()
    self.check_class("pr_status", "row result_%s" % pr.status_slug())
    pr_closed_elem = self.selenium.find_element_by_id("pr_closed")
    pr_closed_html = pr_closed_elem.get_attribute('innerHTML')
    if pr.closed:
      self.assertIn("Closed", pr_closed_html)
    else:
      self.assertIn("Open", pr_closed_html)

  def check_class(self, elem_id, good_class):
    elem = self.selenium.find_element_by_id(elem_id)
    cls = elem.get_attribute("class")
    self.assertEqual(cls, good_class)
    return elem

  def check_elem_bool_class(self, val, elem_id):
    if val:
      return self.check_class(elem_id, "glyphicon glyphicon-ok")
    else:
      return self.check_class(elem_id, "glyphicon glyphicon-remove")

  def check_event(self, ev):
    ev.refresh_from_db()
    self.check_class("event_status", "row result_%s" % ev.status_slug())
    self.check_elem_bool_class(ev.complete, "event_complete")

  def create_event_with_jobs(self, commit='1234', cause=models.Event.PULL_REQUEST):
    ev = utils.create_event(commit2=commit, cause=cause)
    alt_recipe = utils.create_recipe(name="alt recipe", cause=models.Recipe.CAUSE_PULL_REQUEST_ALT)
    utils.create_step(recipe=alt_recipe, position=0)
    utils.create_step(recipe=alt_recipe, position=1)
    if cause == models.Event.PULL_REQUEST:
      pr = utils.create_pr()
      pr.alternate_recipes.add(alt_recipe)
      ev.pull_request = pr
      ev.save()
    r0 = utils.create_recipe(name="r0", cause=cause)
    utils.create_step(recipe=r0, position=1)
    utils.create_step(recipe=r0, position=2)
    r1 = utils.create_recipe(name="r1", cause=cause)
    utils.create_step(recipe=r1, position=1)
    utils.create_step(recipe=r1, position=2)
    r1.depends_on.add(r1)
    utils.create_job(event=ev, recipe=r0)
    utils.create_job(event=ev, recipe=r1)
    return ev

  def check_job(self, job):
    job.refresh_from_db()
    status_row_elem = self.selenium.find_element_by_id("job_status_row")
    self.assertEqual(status_row_elem.get_attribute("class"), "row job_status_%s" % job.status_slug())
    self.check_elem_bool_class(job.complete, "job_complete")
    self.check_elem_bool_class(job.active, "job_active")
    self.check_elem_bool_class(job.ready, "job_ready")
    self.check_elem_bool_class(job.invalidated, "job_invalidated")
    time_elem = self.selenium.find_element_by_id("job_time")
    time_elem_html = time_elem.get_attribute("innerHTML")
    self.assertIn(str(job.seconds), time_elem_html)

    for result in job.step_results.all():
      print("Checking step result %s" % result)
      self.check_class("result_status_%s" % result.pk, "result_%s" % result.status_slug())
      time_elem = self.selenium.find_element_by_id("result_time_%s" % result.pk)
      time_elem_html = time_elem.get_attribute("innerHTML")
      self.assertIn(str(result.seconds), time_elem_html)

      size_elem = self.selenium.find_element_by_id("result_size_%s" % result.pk)
      size_elem_html = size_elem.get_attribute("innerHTML")
      self.assertIn(str(result.output_size()), size_elem_html)

      output_elem = self.selenium.find_element_by_id("result_output_%s" % result.pk)
      output_elem_html = output_elem.get_attribute("innerHTML")
      self.assertIn(str(result.clean_output()), output_elem_html)
