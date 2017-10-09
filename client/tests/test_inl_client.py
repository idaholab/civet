
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
from client import inl_client
import os, shutil, tempfile
from mock import patch

class CommandlineINLClientTests(SimpleTestCase):
    def setUp(self):
        self.log_dir = tempfile.mkdtemp()
        self.orig_home_env = os.environ['HOME']
        os.environ['HOME'] = self.log_dir
        base_dir = '{}/civet'.format(self.log_dir)
        os.mkdir(base_dir)
        base_dir += '/logs'
        os.mkdir(base_dir)

    def tearDown(self):
        shutil.rmtree(self.log_dir)
        os.environ['HOME'] = self.orig_home_env

    def create_client(self, args):
        c, cmd = inl_client.commandline_client(args)
        return c, cmd

    def test_commandline_client(self):
        args = []
        with self.assertRaises(SystemExit):
            c, cmd = inl_client.commandline_client(args)

        # make sure it exits unless all required
        # arguments are passed in
        args.extend(['--client', '0'])
        with self.assertRaises(SystemExit):
            c, cmd = inl_client.commandline_client(args)

        # this is the last required arg
        args.extend(['--daemon', 'stop'])
        c, cmd = inl_client.commandline_client(args)
        self.assertEqual(cmd, 'stop')

    def test_call_daemon(self):
        args = ['--client', '0', '--daemon', 'stop',]
        c, cmd = self.create_client(args)
        # do it like this because it seems mock uses the
        # same instance across calls. so, for example, once start
        # is set it will stay set when we call 'call_daemon' again
        with patch('client.inl_client.ClientDaemon') as mock_daemon:
            inl_client.call_daemon(c, 'start')
            self.assertTrue(mock_daemon.called)
            self.assertTrue(mock_daemon.return_value.start.called)
            self.assertFalse(mock_daemon.return_value.restart.called)
            self.assertFalse(mock_daemon.return_value.stop.called)

        with patch('client.inl_client.ClientDaemon') as mock_daemon:
            inl_client.call_daemon(c, 'stop')
            self.assertTrue(mock_daemon.called)
            self.assertFalse(mock_daemon.return_value.start.called)
            self.assertFalse(mock_daemon.return_value.restart.called)
            self.assertTrue(mock_daemon.return_value.stop.called)

        with patch('client.inl_client.ClientDaemon') as mock_daemon:
            inl_client.call_daemon(c, 'restart')
            self.assertTrue(mock_daemon.called)
            self.assertFalse(mock_daemon.return_value.start.called)
            self.assertTrue(mock_daemon.return_value.restart.called)
            self.assertFalse(mock_daemon.return_value.stop.called)

    @patch.object(inl_client, 'call_daemon')
    def test_main(self, mock_daemon):
        mock_daemon.return_value = None
        args = ['--client', '0', '--daemon', 'stop',]
        inl_client.main(args)
