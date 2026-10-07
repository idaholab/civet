# Copyright 2016-2025 Battelle Energy Alliance, LLC
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

from __future__ import unicode_literals, absolute_import
from django.test import SimpleTestCase
from django.test import override_settings
from client import BaseClient
from client.tests import utils
from ci.tests import utils as test_utils
from mock import patch
import os, tempfile


@override_settings(INSTALLED_GITSERVERS=[test_utils.github_config()])
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
        self.assertIn("test_log", c.client_info["log_file"])

        # can't write
        with self.assertRaises(BaseClient.ClientException):
            c.set_log_file("/var/foo")

        # can't write
        with self.assertRaises(BaseClient.ClientException):
            c.set_log_file("/aafafafaf/fo")

        # not set, should just return
        c.set_log_file("")

    def test_get_client_info(self):
        c = utils.create_base_client()

        with self.assertRaises(BaseClient.ClientException):
            c.get_client_info("foo")

        self.assertEqual(c.get_client_info("client_name"), c.client_info["client_name"])

    def test_set_client_info(self):
        c = utils.create_base_client()

        with self.assertRaises(BaseClient.ClientException):
            c.set_client_info("foo", None)

        c.set_client_info("client_name", "foo")
        self.assertEqual(c.get_client_info("client_name"), "foo")

    def test_add_config(self):
        with self.assertRaises(BaseClient.ClientException):
            c = utils.create_base_client()
            c.add_config(1)
        with self.assertRaises(BaseClient.ClientException):
            c = utils.create_base_client()
            c.add_config("foo")
            c.add_config("foo")
        c = utils.create_base_client()
        c.add_config("bar")

    def test_environment(self):
        c = utils.create_base_client()
        self.assertNotIn("FOO", c.get_environment())
        with self.assertRaises(BaseClient.ClientException):
            c.get_environment("FOO")
        c.set_environment("FOO", "bar")
        self.assertEqual("bar", c.get_environment("FOO"))
        self.assertEqual(c.client_info["environment"], c.get_environment())

    def test_read_build_key(self):
        with tempfile.TemporaryDirectory() as key_dir:
            path = os.path.join(key_dir, "build_key")
            # Doesn't exist
            with self.assertRaises(BaseClient.ClientException):
                BaseClient.read_build_key(path)

            # Empty
            utils.write_build_key_file(path, " \n ")
            with self.assertRaises(BaseClient.ClientException):
                BaseClient.read_build_key(path)

            # The whitespace is stripped
            utils.write_build_key_file(path, " the_key\n")
            with self.assertNoLogs("civet_client", level="WARNING"):
                self.assertEqual(BaseClient.read_build_key(path), "the_key")

            # ~ is expanded
            with patch.dict(os.environ, {"HOME": key_dir}):
                self.assertEqual(BaseClient.read_build_key("~/build_key"), "the_key")

            # Warns if other users can read it
            for mode in [0o640, 0o604]:
                os.chmod(path, mode)
                with self.assertLogs("civet_client", level="WARNING") as logs:
                    self.assertEqual(BaseClient.read_build_key(path), "the_key")
                self.assertIn("can be read by other users", logs.output[0])
                self.assertNotIn("the_key", logs.output[0])
            # But not if they can only write it
            os.chmod(path, 0o622)
            with self.assertNoLogs("civet_client", level="WARNING"):
                BaseClient.read_build_key(path)

    @patch.object(BaseClient, "ServerUpdater")
    @patch.object(BaseClient, "JobRunner")
    def test_run_claimed_job_multiple_servers(self, mock_runner, mock_updater):
        c = utils.create_base_client()
        mock_runner.return_value.error = False
        mock_runner.return_value.job_killed = False
        c.client_info["build_keys"] = {"server0": "key0", "server1": "key1"}
        claimed = {"job_info": {"job_id": 1, "recipe_name": "foo"}}
        c.run_claimed_job("server0", ["server0", "server1"], claimed)
        mock_runner.return_value.run_job.assert_called_once_with(fail=False)
        # The runner uses the key for the server
        self.assertEqual(mock_runner.call_args[0][4], "key0")
        control_q = mock_updater.call_args[0][4]
        self.assertEqual(
            control_q.get(block=False),
            {"server": "server0", "message": "Job 1: foo"},
        )
        self.assertEqual(
            control_q.get(block=False),
            {"server": "server1", "message": "Running job on another server"},
        )
        self.assertEqual(control_q.get(block=False), {"command": "Quit"})
        self.assertFalse(c.runner_error)
        self.assertFalse(c.runner_killed)

    @patch.object(BaseClient.time, "sleep")
    @patch.object(BaseClient.JobGetter, "get_job")
    def test_run_poll(self, mock_get_job, mock_sleep):
        c = utils.create_base_client()
        c.client_info["single_shot"] = False
        mock_get_job.return_value = None

        # Exit the loop after the first poll
        def stop_polling(seconds):
            c.client_info["single_shot"] = True

        mock_sleep.side_effect = stop_polling
        c.run()
        self.assertEqual(mock_get_job.call_count, 2)
        mock_sleep.assert_called_once_with(c.get_client_info("poll"))
