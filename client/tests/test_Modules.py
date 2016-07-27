
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
from client import Modules
import os

class ModulesTest(SimpleTestCase):
  def setUp(self):
    self.home = os.environ["MODULESHOME"]

  def tearDown(self):
    os.environ["MODULESHOME"] = self.home

  def test_init(self):
    Modules.Modules() # make sure it works first
    del os.environ["MODULESHOME"]
    with self.assertRaises(Exception):
      Modules.Modules()

  def check_module_return(self, ret, success=True, stdout="", stderr=""):
    self.assertEqual(ret["success"], success)
    self.assertEqual(ret["stdout"], stdout)
    self.assertNotEqual(ret["stderr"], stderr)

  def test_command(self):
    mod = Modules.Modules()
    # We don't know what modules are loaded at the moment, so purge first
    ret = mod.command("purge")
    self.assertEqual(ret["success"], True)
    self.assertEqual(ret["stderr"], "")

    # List should still put something on stderr
    ret = mod.command("list")
    self.assertEqual(ret["success"], True)
    self.assertEqual(ret["stdout"], "")
    self.assertNotEqual(ret["stderr"], "")

    # doing another purge shouldn't do anything
    ret = mod.command("purge")
    self.assertEqual(ret["success"], True)
    self.assertEqual(ret["stdout"], "")
    self.assertEqual(ret["stderr"], "")

    # load a module, should provide command on stdout
    ret = mod.command("load", ["moose-dev-gcc"])
    self.assertEqual(ret["success"], True)
    self.assertNotEqual(ret["stdout"], "")
    self.assertIn("os.environ", ret["stdout"])
    self.assertEqual(ret["stderr"], "")

    # now purge should put something on stdout
    ret = mod.command("purge")
    self.assertEqual(ret["success"], True)
    self.assertNotEqual(ret["stdout"], "")
    self.assertIn("os.environ", ret["stdout"])
    self.assertEqual(ret["stderr"], "")

    # Bad command
    ret = mod.command("foo")
    self.assertEqual(ret["success"], False)
    self.assertEqual(ret["stdout"], "")
    self.assertNotEqual(ret["stderr"], "")

    # load bad module
    ret = mod.command("load", ["does not exist"])
    self.assertEqual(ret["success"], True)
    self.assertEqual(ret["stdout"], "")
    self.assertNotEqual(ret["stderr"], "")

  def test_clear_and_load(self):
    mod = Modules.Modules()

    # load bad module
    with self.assertRaises(Exception):
      mod.clear_and_load(["does not exist"])

    # load good module
    mod.clear_and_load(["moose-dev-gcc"])
    ret = mod.command("list")
    self.assertIn("moose-dev-gcc", ret["stderr"])
