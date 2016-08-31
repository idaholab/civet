
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

import DBTester
from ci import TimeUtils
import datetime

class Tests(DBTester.DBTester):
  def test_sortable_time_str(self):
    TimeUtils.sortable_time_str(datetime.datetime.now())

  def test_display_time_str(self):
    TimeUtils.display_time_str(datetime.datetime.now())

  def test_human_time_str(self):
    TimeUtils.human_time_str(datetime.datetime.now())

  def test_get_local_timestamp(self):
    TimeUtils.get_local_timestamp()

  def test_std_time_str(self):
    TimeUtils.std_time_str(datetime.datetime.now())
