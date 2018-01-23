
# Copyright 2016 Battelle Energy Alliance, LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from __future__ import unicode_literals
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from ci.tests import DBTester
from . import utils

class LiveClientTester(StaticLiveServerTestCase, DBTester.DBCompare):
    def setUp(self):
        super(LiveClientTester, self).setUp()
        self.client_info = utils.default_client_info()
        self.client_info["servers"] = [self.live_server_url]
        self.client_info["server"] = self.live_server_url
        self.client_info["update_step_time"] = 1
        self.client_info["server_update_interval"] = 1
