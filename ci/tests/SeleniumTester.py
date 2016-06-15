from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from selenium import webdriver
import functools
from selenium.webdriver.support.wait import WebDriverWait
from django.conf import settings

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

class SeleniumTester(StaticLiveServerTestCase):
  fixtures = ['base.json']

  selenium = None

  @classmethod
  def setUpClass(cls):
    cls.drivers = WebDriverList(
        cls.create_chrome_driver(),
#        cls.create_firefox_driver(),
        )
    super(SeleniumTester, cls).setUpClass()

  @classmethod
  def tearDownClass(cls):
    cls.drivers.quit()
    super(SeleniumTester, cls).tearDownClass()

  @classmethod
  def create_chrome_driver(cls):
    """
    Get the chromedriver from:
    https://sites.google.com/a/chromium.org/chromedriver/
    and put it your path
    """
    return webdriver.Chrome()

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
    return webdriver.Firefox(capabilities=cap)

  def setUp(self):
    self.orig_home_interval = settings.HOME_PAGE_UPDATE_INTERVAL
    self.orig_job_interval = settings.JOB_PAGE_UPDATE_INTERVAL
    self.orig_event_interval = settings.EVENT_PAGE_UPDATE_INTERVAL
    settings.HOME_PAGE_UPDATE_INTERVAL = 1000
    settings.JOB_PAGE_UPDATE_INTERVAL = 1000
    settings.EVENT_PAGE_UPDATE_INTERVAL = 1000

  def tearDown(self):
    settings.HOME_PAGE_UPDATE_INTERVAL = self.orig_home_interval
    settings.JOB_PAGE_UPDATE_INTERVAL = self.orig_job_interval
    settings.EVENT_PAGE_UPDATE_INTERVAL = self.orig_event_interval


  def wait_for_load(self, timeout=2):
    WebDriverWait(self.selenium, timeout).until(lambda driver: driver.find_element_by_tag_name('body'))
