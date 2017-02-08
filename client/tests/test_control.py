
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
from client import control
from mock import patch
import multiprocessing
import select, os

class ConnectionTest(object):
    def __init__(self, recv_msg=None):
        self.recv_msg =recv_msg
        self.send_msg = None

    def recv(self, size):
        return self.recv_msg

    def send(self, msg):
        self.send_msg = msg

    def close(self):
        pass

class SocketTest(object):
    def __init__(self, conn):
        self.conn = conn

    def accept(self):
        return self.conn, None

class PopenTest(object):
    def __init__(self, poll_ret=0):
        self.poll_ret = poll_ret
        self.pid = -20

    def poll(self):
        return self.poll_ret

    def terminate(self):
        pass

class Tests(SimpleTestCase):
    def setUp(self):
        control.ClientsController.FILE_SOCKET = "/tmp/test_civet_client_controller.sock"
        control.ControlDaemon.PID_FILE = "/tmp/test_civet_client_controller.pid"
        control.ClientsController.remove_socket()
        self.controller = None
        self.controller_proc = None

    def tearDown(self):
        if self.controller_proc:
            self.controller_proc.terminate()
            try:
                control.main(["--shutdown"])
            except:
                pass
        control.ClientsController.remove_socket()

    def start_controller(self):
        self.controller = control.ClientsController()
        self.controller_proc = multiprocessing.Process(target=self.controller.run)
        self.controller_proc.start()

    @patch.object(control.ClientsController, 'run')
    @patch.object(control.ControlDaemon, 'start')
    @patch.object(control.ClientsController, 'send_cmd')
    def test_main(self, mock_cmd, mock_daemon, mock_controller_run):
        mock_controller_run.return_value = 0
        mock_daemon.return_value = 0
        mock_cmd.return_value = 0
        self.assertEqual(control.main([]), 1)
        self.assertEqual(control.main(["--launch", "--no-daemon"]), 0)
        self.assertEqual(control.main(["--launch"]), 0)
        self.assertEqual(control.main(["--stop"]), 0)
        self.assertEqual(control.main(["--start"]), 0)
        self.assertEqual(control.main(["--graceful"]), 0)
        self.assertEqual(control.main(["--graceful-restart"]), 0)
        self.assertEqual(control.main(["--restart"]), 0)
        self.assertEqual(control.main(["--status"]), 0)
        self.assertEqual(control.main(["--shutdown"]), 0)

    def test_controller(self):
        controller = control.ClientsController()
        controller.shutdown = True
        self.assertEqual(controller.run(), 0)

    def default_processes(self):
        return {
            0: {"process": PopenTest(None), "start": 0, "running": True},
            1: {"process": PopenTest(0), "start": 1, "running": False, "need_restart": True},
            2: {"process": PopenTest(0), "start": 1, "running": True},
            }

    def check_cmd(self, cmd, mock_select, ready=True, no_data=False):
        controller = control.ClientsController()
        controller.processes = self.default_processes()
        c = ConnectionTest(cmd)
        s = SocketTest(c)
        controller.socket = s
        if ready:
            mock_select.return_value = [s], [], []
        else:
            mock_select.return_value = [], [], []
        controller.read_cmd()
        if not no_data:
            self.assertNotEqual(c.send_msg, None)
        else:
            self.assertEqual(c.send_msg, None)

    @patch.object(select, "select")
    @patch.object(os, 'kill')
    def test_read_cmd(self, mock_kill, mock_select):
        mock_kill.return_value = 0
        self.check_cmd("unknown", mock_select, ready=False, no_data=True)
        self.check_cmd("", mock_select, no_data=True)
        self.check_cmd("unknown", mock_select)
        self.check_cmd("stop", mock_select)
        self.check_cmd("start", mock_select)
        self.check_cmd("restart", mock_select)
        self.check_cmd("graceful_restart", mock_select)
        self.check_cmd("graceful", mock_select)
        self.check_cmd("status", mock_select)
        self.check_cmd("shutdown", mock_select)

    @patch.object(control.ClientsController, 'start_proc')
    def test_check_restart(self, mock_start):
        mock_start.return_value = 0
        controller = control.ClientsController()
        controller.processes = self.default_processes()
        controller.check_restart()

    def test_check_dead(self):
        controller = control.ClientsController()
        controller.processes = self.default_processes()
        controller.check_dead()
