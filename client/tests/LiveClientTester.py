from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from ci.tests import DBTester
import utils

class LiveClientTester(StaticLiveServerTestCase, DBTester.DBCompare):
  def setUp(self):
    super(LiveClientTester, self).setUp()
    self._setup_recipe_dir()
    self._set_cache_timeout()
    self.client_info = utils.default_client_info()
    self.client_info["servers"] = [self.live_server_url]
    self.client_info["server"] = self.live_server_url
    self.client_info["update_step_time"] = 1
    self.client_info["server_update_interval"] = 1

  def tearDown(self):
    super(LiveClientTester, self).tearDown()
    self._cleanup()
