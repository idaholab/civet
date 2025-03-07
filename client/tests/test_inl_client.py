
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
from ci.tests import utils as test_utils
from client import inl_client, BaseClient
import os, shutil, tempfile, pwd
from mock import patch

@override_settings(INSTALLED_GITSERVERS=[test_utils.github_config()])
class CommandlineINLClientTests(SimpleTestCase):
    def setUp(self):
        self.log_dir = tempfile.mkdtemp()
        self.orig_home_env = os.environ['HOME']
        self.orig_civet_home_env = os.environ.get('CIVET_HOME', None)
        if self.orig_civet_home_env:
            del os.environ['CIVET_HOME']
        os.environ['HOME'] = self.log_dir
        self.civet_dir = '{}/civet'.format(self.log_dir)
        os.mkdir(self.civet_dir)
        logs_dir = self.civet_dir + '/logs'
        os.mkdir(logs_dir)

    def tearDown(self):
        shutil.rmtree(self.log_dir)
        os.environ['HOME'] = self.orig_home_env
        if self.orig_civet_home_env:
            os.environ['CIVET_HOME'] = self.orig_civet_home_env

    def create_client(self, args):
        c, cmd = inl_client.commandline_client(args)
        return c, cmd

    def test_commandline_client(self):
        args = []
        # Missing --daemon, --client
        with self.assertRaises(SystemExit):
            inl_client.commandline_client(args)

        # Missing --daemon
        args.extend(['--client', '0'])
        with self.assertRaises(SystemExit):
            inl_client.commandline_client(args)

        # this is the last required arg
        args.extend(['--daemon', 'stop'])
        c, cmd = inl_client.commandline_client(args)
        self.assertEqual(cmd, 'stop')

    def test_commandline_client_start_restart_args(self):
        def do_test(test_cmd):
            args = ['--client', '0', '--daemon', test_cmd]

            # Missing --configs
            with self.assertRaises(BaseClient.ClientException):
                inl_client.commandline_client(args)

            # Have all required args
            args.extend(['--configs', 'config'])
            c, cmd = inl_client.commandline_client(args)
            self.assertEqual(self.civet_dir + '/build_0', c.get_build_root())

            # Addd --build-root
            args.extend(['--build-root', '/foo/bar'])
            c, cmd = inl_client.commandline_client(args)
            self.assertIn('config', c.get_client_info('build_configs'))
            self.assertEqual('/foo/bar', c.get_build_root())
            self.assertEqual(c.get_environment('CIVET_CLIENT_NUMBER'), '0')
            self.assertEqual(cmd, test_cmd)

            # Should add env
            args.extend(['--env', 'FOO', 'bar'])
            c, cmd = inl_client.commandline_client(args)
            self.assertEqual('bar', c.get_environment('FOO'))

            # Should add the current user to the client name
            user = pwd.getpwuid(os.getuid())[0]
            args.extend(['--user-client-suffix'])
            c, cmd = inl_client.commandline_client(args)
            self.assertIn(user, c.get_client_info('client_name'))
            self.assertIn(user, c.get_environment('CIVET_CLIENT_NAME'))

        do_test('start')
        do_test('restart')

    def test_call_daemon(self):
        args = ['--client', '0', '--configs', 'config', '--daemon', 'stop', '--build-root', '/foo/bar']
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
        args = ['--client', '0', '--configs', 'config', '--daemon', 'stop', '--build-root', '/foo/bar']
        inl_client.main(args)
