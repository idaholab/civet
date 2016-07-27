
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

from django.test import SimpleTestCase
from client import BaseClient
from . import utils

class Tests(SimpleTestCase):
  def test_log_dir(self):
    c = utils.create_base_client()
    self.assertIn(c.client_info["client_name"], c.client_info["log_file"])
    # dir exists but can't write
    with self.assertRaises(BaseClient.ClientException):
      c.set_log_dir("/var")

    # dir does not exist
    with self.assertRaises(BaseClient.ClientException):
      c.set_log_dir("/var/aafafafaf")

    # not set, should just return
    c.set_log_dir("")

    # test it out from __init__
    with self.assertRaises(BaseClient.ClientException):
      c = utils.create_base_client(log_dir="/afafafafa/")

    # test it out from __init__
    with self.assertRaises(BaseClient.ClientException):
      c = utils.create_base_client(log_dir="", log_file="")

  def test_log_file(self):
    c = utils.create_base_client(log_file="test_log")
    self.assertIn('test_log', c.client_info["log_file"])

    # can't write
    with self.assertRaises(BaseClient.ClientException):
      c.set_log_file("/var/foo")

    # can't write
    with self.assertRaises(BaseClient.ClientException):
      c.set_log_file("/aafafafaf/fo")

    # not set, should just return
    c.set_log_file("")
