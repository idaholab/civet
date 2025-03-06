
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

from __future__ import unicode_literals, absolute_import
from django.test import SimpleTestCase
from django.test import override_settings
from ci.tests import utils as test_utils
from client import JobRunner, BaseClient
from client.tests import utils
import os, platform
from distutils import spawn
from mock import patch
import subprocess
BaseClient.setup_logger()

try:
    from queue import Queue, Empty
except ImportError:
    from Queue import Queue, Empty

@override_settings(INSTALLED_GITSERVERS=[test_utils.github_config()])
class Tests(SimpleTestCase):
    def setUp(self):
        self.build_root = "/foo/bar"
        self.message_q = Queue()
        self.command_q = Queue()

    def create_runner(self):
        client_info = utils.default_client_info()
        client_info['environment']['BUILD_ROOT'] = self.build_root
        job_info = utils.create_job_dict()
        runner = JobRunner.JobRunner(client_info, job_info, self.message_q, self.command_q, 1234)
        self.assertEqual(runner.canceled, False)
        self.assertEqual(runner.stopped, False)
        self.assertEqual(runner.local_env["var_with_root"], "%s/bar" % self.build_root)
        self.assertEqual(runner.job_data["steps"][0]["environment"]["step_var_with_root"], "%s/foo" % self.build_root)
        return runner

    def check_job_results(self, results, runner, complete=True, canceled=False, failed=False):
        self.assertEqual(results['complete'], complete)
        self.assertEqual(results['canceled'], canceled)
        self.assertEqual(results['failed'], failed)
        self.assertIn('seconds', results)
        self.assertEqual(results['client_name'], runner.client_info["client_name"])
        self.assertEqual(self.message_q.qsize(), 1)
        msg = self.message_q.get(block=False)
        self.assertEqual(len(msg), 4)
        server = runner.client_info["server"]
        self.assertEqual(msg["server"], server)
        self.assertTrue(msg["url"].startswith(server))
        self.assertEqual(msg["job_id"], runner.job_data["job_id"])
        self.assertEqual(msg["payload"], results)

    @patch.object(JobRunner.JobRunner, 'run_step')
    def test_run_job(self, mock_run_step):
        r = self.create_runner()

        run_step_results = {'canceled': False, 'exit_status': 0}
        mock_run_step.return_value = run_step_results

        # normal run
        results = r.run_job()
        self.assertFalse(r.job_killed)
        self.assertFalse(r.canceled)
        self.assertFalse(r.stopped)
        self.assertFalse(r.error)
        self.check_job_results(results, r)

        # test bad exit_status
        run_step_results['exit_status'] = 1
        mock_run_step.return_value = run_step_results

        self.assertEqual(r.job_data["steps"][0]["abort_on_failure"], True)
        results = r.run_job()
        self.check_job_results(results, r, failed=True)

        # bad exit_status but don't abort
        r.job_data["steps"][0]["abort_on_failure"] = False
        results = r.run_job()
        self.check_job_results(results, r)

        # test canceled
        r.canceled = True
        results = r.run_job()
        self.check_job_results(results, r, canceled=True)

        # test stopped
        r.canceled = False
        r.stopped = True
        results = r.run_job()
        self.check_job_results(results, r)

        # test error
        r.canceled = False
        r.stopped = False
        r.error = True
        results = r.run_job()
        self.check_job_results(results, r, canceled=True, failed=True)

        # test skipped
        r.canceled = False
        r.stopped = False
        r.error = False
        run_step_results['exit_status'] = 86
        mock_run_step.return_value = run_step_results
        results = r.run_job()
        self.check_job_results(results, r)

    def test_update_step(self):
        r = self.create_runner()
        step = {'step_num': 1, 'stepresult_id': 1}
        chunk_data = {"message": "message"}
        for stage in ["start", "complete", "update"]:
            chunk_data["message"] = stage
            r.update_step(stage, step, chunk_data)
            self.assertEqual(self.message_q.qsize(), 1)
            msg = self.message_q.get(block=False)
            self.assertEqual(len(msg), 4)
            server = r.client_info["server"]
            self.assertEqual(msg["server"], server)
            self.assertTrue(msg["url"].startswith(server))
            self.assertIn(stage, msg["url"])
            self.assertEqual(msg["job_id"], r.job_data["job_id"])
            self.assertEqual(msg["payload"], chunk_data)

    def test_get_output_from_queue(self):
        r = self.create_runner()
        q0 = {"msg": 1}
        q1 = {"msg": 2}
        self.message_q.put(q0)
        self.message_q.put(q1)
        output = r.get_output_from_queue(self.message_q)
        self.assertEqual(len(output), 2)
        self.assertEqual(output[0], q0)
        self.assertEqual(output[1], q1)

    def test_read_command(self):
        r = self.create_runner()
        # test a command to another job
        cmd = {"job_id": r.job_data["job_id"], "command": "cancel"}

        # Test cancel command
        cmd["job_id"] = r.job_data["job_id"]
        self.assertEqual(r.canceled, False)
        self.command_q.put(cmd)
        r.read_command()
        self.assertEqual(r.canceled, True)

        # Test stop command
        cmd["command"] = "stop"
        self.command_q.put(cmd)
        r.canceled = False
        self.assertEqual(r.stopped, False)
        r.read_command()
        self.assertEqual(r.stopped, True)

        # Test unknown command
        cmd["command"] = "unknown"
        self.command_q.put(cmd)
        r.stopped = False
        r.read_command()
        self.assertEqual(r.stopped, False)
        self.assertEqual(r.canceled, False)

        # Test bad command message
        self.command_q.put({})
        r.read_command()

    def test_read_process_output(self):
        r = self.create_runner()
        r.client_info["update_step_time"] = 1
        with JobRunner.temp_file() as script_file:
            script = b"for i in $(seq 5);do echo start $i; sleep 1; echo done $i; done"
            script_file.write(script)
            script_file.close()
            with open(os.devnull, "wb") as devnull:
                proc = r.create_process(script_file.name, {}, devnull)
                # standard run of the subprocess, just check we get all the output
                out = r.read_process_output(proc, r.job_data["steps"][0], {})
                proc.wait()
                test_out = ""
                self.assertGreater(self.message_q.qsize(), 3)
                msg_list = []
                try:
                    while True:
                        l = self.message_q.get(block=False)
                        msg_list.append(l)
                except Empty:
                    pass

                for i in range(1, 6):
                    start = "start {}\n".format(i)
                    done = "done {}\n".format(i)
                    if i < 4:
                        # only do this test for the first few
                        # since there is no guarentee that update_step()
                        # will get called for all of them before the
                        # process terminates
                        found_start = False
                        found_done = False
                        for msg in msg_list:
                            if start.strip() in msg["payload"]["output"]:
                                found_start = True
                            if done.strip() in msg["payload"]["output"]:
                                found_done = True
                        self.assertTrue(found_start)
                        self.assertTrue(found_done)
                    test_out += start + done

                self.assertEqual(test_out, out["output"])
                self.assertEqual(out["complete"], True)
                self.assertGreater(out["time"], 1)

                proc = r.create_process(script_file.name, {}, devnull)
                # Test cancel while reading output
                self.command_q.put({"job_id": r.job_data["job_id"], "command": "cancel"})
                self.assertEqual(r.canceled, False)
                self.assertFalse(r.job_killed)
                r.read_process_output(proc, r.job_data["steps"][0], {})
                proc.wait()
                self.assertEqual(r.canceled, True)
                self.assertTrue(r.job_killed)

    def test_read_over_max_output(self):
        r = self.create_runner()
        r.client_info["update_step_time"] = 1
        r.max_output_size = 1024
        with JobRunner.temp_file() as script_file:
            script = b"for i in $(seq 5);do for j in $(seq 5);do for k in $(seq 5);do echo start $i-$j-$k; echo done $i-$j-$k; done; done; done"
            script_file.write(script)
            script_file.close()
            with open(os.devnull, "wb") as devnull:
                proc = r.create_process(script_file.name, {}, devnull)
                # standard run of the subprocess
                # check we get the start and end of the output but not middle
                out = r.read_process_output(proc, r.job_data["steps"][0], {})
                proc.wait()

                self.assertIn("start 1-1-1", out["output"])
                self.assertIn("start 1-3-5", out["output"])
                self.assertTrue("start 3-2-1" not in out["output"])
                self.assertIn("Output size exceeded", out["output"])
                self.assertIn("start 5-3-1", out["output"])
                self.assertIn("start 5-5-5", out["output"])

    def test_kill_job(self):
        with JobRunner.temp_file() as script:
            script.write(b"sleep 30")
            script.close()
            with open(os.devnull, "wb") as devnull:
                r = self.create_runner()
                proc = r.create_process(script.name, {}, devnull)
                self.assertFalse(r.job_killed)
                r.kill_job(proc)
                self.assertEqual(proc.poll(), -15) # SIGTERM
                proc.wait()
                self.assertTrue(r.job_killed)
                # get some coverage when the proc is already dead
                r.kill_job(proc)
                self.assertTrue(r.job_killed)

                # the kill path for windows is different, just get some
                # coverage because we don't currently have a windows box
                # to test on
                with patch.object(platform, 'system') as mock_system:
                    mock_system.side_effect = ["linux", "Windows"]
                    proc = r.create_process(script.name, {}, devnull)
                    r.kill_job(proc)

                    with patch.object(spawn, 'find_executable') as mock_find:
                        mock_system.side_effect = ["Windows"]
                        mock_find.return_value = True
                        r.kill_job(proc)

                # mimic not being able to kill the job
                with patch.object(subprocess.Popen, 'poll') as mock_poll, patch.object(subprocess.Popen, 'kill') as mock_kill:
                    mock_poll.side_effect = [True, None, None]
                    mock_kill.return_value = False
                    proc = r.create_process(script.name, {}, devnull)
                    r.kill_job(proc)


    def test_run_step(self):
        r = self.create_runner()
        r.client_info["update_step_time"] = 1

        step_env_orig = r.job_data["steps"][0]["environment"].copy()
        global_env_orig = r.global_env.copy()
        results = r.run_step(r.job_data["steps"][0])
        self.assertIn('test_output1', results['output'])
        self.assertIn('test_output2', results['output'])
        self.assertEqual(results['exit_status'], 0)
        self.assertEqual(results['canceled'], False)
        self.assertFalse(r.job_killed)
        self.assertGreater(results['time'], 1)
        # Make sure run_step doesn't touch the environment
        self.assertEqual(r.global_env, global_env_orig)
        self.assertEqual(r.job_data["steps"][0]["environment"], step_env_orig)

        # Test output size limits work
        r.max_output_size = 10
        results = r.run_step(r.job_data["steps"][0])
        self.assertIn('command not found', results['output'])
        self.assertIn('Output size exceeded limit', results['output'])
        self.assertFalse(r.job_killed)

        self.command_q.put({"job_id": r.job_data["job_id"], "command": "cancel"})
        results = r.run_step(r.job_data["steps"][0])
        self.assertEqual(results['canceled'], True)
        self.assertEqual(r.canceled, True)
        self.assertTrue(r.job_killed)

        # just get some coverage
        with patch.object(JobRunner.JobRunner, "read_process_output") as mock_proc:
            r.canceled = False
            mock_proc.side_effect = Exception("Oh no!")
            results = r.run_step(r.job_data["steps"][0])
            self.assertEqual(results['canceled'], True)
            self.assertEqual(r.canceled, True)
            self.assertTrue(r.job_killed)

        # Simulate out of disk space error
        with patch.object(JobRunner.JobRunner, "run_step_process") as mock_run:
            r.canceled = False
            mock_run.side_effect = IOError("Oh no!")
            results = r.run_step(r.job_data["steps"][0])
            self.assertEqual(results['exit_status'], 1)
            self.assertEqual(r.canceled, False)
            self.assertEqual(r.error, True)
            self.assertTrue(r.job_killed)

    @patch.object(platform, 'system')
    def test_run_step_platform(self, mock_system):
        r = self.create_runner()
        r.client_info["update_step_time"] = 1

        # Don't have a Windows box to test on but
        # we can get some basic coverage
        mock_system.return_value = "Windows"
        # the windows command won't work
        data = r.run_step(r.job_data["steps"][0])
        self.assertEqual(data["time"], 0)
        self.assertEqual(r.stopped, True)

    def test_env_dict(self):
        r = self.create_runner()
        env = {"name": "value", "other": "value"}
        new_env = r.env_to_dict(env)
        self.assertEqual(env, new_env)
        r.env_to_dict([("name", "value"), ("other", "value")])
        self.assertEqual(env, new_env)
        new_env = r.env_to_dict(("name", "value"))
        self.assertEqual({}, new_env)

        env["another"] = "BUILD_ROOT/foo"
        test_env = env.copy()
        r.clean_env(test_env)
        self.assertEqual(test_env["another"], "%s/foo" % self.build_root)
        test_env = env.copy()
        del r.client_info['environment']['BUILD_ROOT']
        r.clean_env(test_env)
        self.assertEqual(test_env["another"], "%s/foo" % os.getcwd())

    def test_max_step_time(self):
        with JobRunner.temp_file() as script:
            script.write(b"sleep 30")
            script.close()
            with open(os.devnull, "wb") as devnull:
                r = self.create_runner()
                r.max_step_time = 2
                proc = r.create_process(script.name, {}, devnull)
                out = r.read_process_output(proc, r.job_data["steps"][0], {})
                self.assertIn("taking longer than the max", out["output"])
                self.assertLess(out["time"], 10)
                self.assertEqual(out["canceled"], True)
                self.assertTrue(r.job_killed)

    def test_max_step_time_and_output(self):
        with JobRunner.temp_file() as script_file:
            script = b"for i in $(seq 5);do for j in $(seq 5);do for k in $(seq 5);do echo start $i-$j-$k; echo done $i-$j-$k; done; done; done; sleep 30"
            script_file.write(script)
            script_file.close()
            with open(os.devnull, "wb") as devnull:
                r = self.create_runner()
                r.client_info["update_step_time"] = 1
                r.max_output_size = 1024
                r.max_step_time = 4
                proc = r.create_process(script_file.name, {}, devnull)
                out = r.read_process_output(proc, r.job_data["steps"][0], {})

                self.assertIn("start 1-1-1", out["output"])
                self.assertIn("start 1-3-5", out["output"])
                self.assertTrue("start 3-2-1" not in out["output"])
                self.assertIn("Output size exceeded", out["output"])
                self.assertIn("start 5-3-1", out["output"])
                self.assertIn("start 5-5-5", out["output"])

                self.assertIn("taking longer than the max", out["output"])
                self.assertLess(out["time"], 10)
                self.assertEqual(out["canceled"], True)
                self.assertTrue(r.job_killed)
