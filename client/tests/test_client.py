
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
from client import client, BaseClient
from client.tests import utils
import os
from mock import patch


@override_settings(INSTALLED_GITSERVERS=[test_utils.github_config()])
class CommandlineClientTests(SimpleTestCase):

    def test_commandline_client(self):
        args = []

        # Missing --url, --build-key, --name
        with self.assertRaises(SystemExit):
            c, cmd = client.commandline_client(args)

        # Missing --build-key, --name
        args.extend(['--url', 'testUrl'])
        with self.assertRaises(SystemExit):
            c, cmd = client.commandline_client(args)

        # Missing --name
        args.extend(['--build-key', '123'])
        with self.assertRaises(SystemExit):
            c, cmd = client.commandline_client(args)

        # this is the last required arg
        args.extend(['--name', 'testName'])
        c, cmd = client.commandline_client(args)

        good_args = args

        self.assertEqual(c.client_info["server"], 'testUrl')
        self.assertEqual(c.client_info["build_keys"][0], '123')
        self.assertEqual(c.client_info["client_name"], 'testName')

        args.extend([
            '--single-shot',
            '--poll',
            '1',
            '--log-dir',
            '/tmp',
            '--insecure',
            ])

        c, cmd = client.commandline_client(args)
        self.assertEqual(c.client_info["single_shot"], True)
        self.assertEqual(c.client_info["ssl_verify"], False)
        self.assertEqual(c.client_info["poll"], 1)
        self.assertEqual('/tmp', os.path.dirname(c.client_info["log_file"]))

        args.extend([ '--ssl-cert', 'my_cert'])
        args.extend([ '--log-file', '/tmp/testFile'])
        c, cmd = client.commandline_client(args)
        self.assertEqual(c.client_info["log_file"], '/tmp/testFile')
        self.assertEqual(c.client_info["ssl_verify"], 'my_cert')

        args = good_args
        args.extend(['--daemon', 'start'])
        # Missing --configs
        with self.assertRaises(BaseClient.ClientException):
            client.commandline_client(args)
        args.extend(['--configs', 'config'])
        c, cmd = client.commandline_client(args)
        self.assertIn('config', c.get_client_info('build_configs'))
        self.assertEqual(cmd, 'start')


        args.extend(['--env', 'FOO', 'bar'])
        c, cmd = client.commandline_client(args)
        self.assertEqual('bar', c.get_environment('FOO'))

        build_root_before = os.environ.get('BUILD_ROOT', None)
        os.environ['BUILD_ROOT'] = '/foo/bar'
        c, cmd = client.commandline_client(args)
        self.assertEqual('/foo/bar', c.get_environment('BUILD_ROOT'))
        if build_root_before:
            os.environ['BUILD_ROOT'] = build_root_before
        else:
            del os.environ['BUILD_ROOT']

        args = good_args
        args.extend(['--daemon', 'stop'])
        c, cmd = client.commandline_client(args)
        self.assertEqual(cmd, 'stop')

        args = good_args
        args.extend(['--daemon', 'restart'])
        c, cmd = client.commandline_client(args)
        self.assertEqual(cmd, 'restart')

        args = good_args
        args.extend(['--daemon', 'foo'])
        with self.assertRaises(SystemExit):
            c, cmd = client.commandline_client(args)

    def test_call_daemon(self):
        c = utils.create_base_client()
        # do it like this because it seems mock uses the
        # same instance across calls. so, for example, once start
        # is set it will stay set when we call 'call_daemon' again
        with patch('client.client.ClientDaemon') as mock_daemon:
            client.call_daemon(c, 'start')
            self.assertTrue(mock_daemon.called)
            self.assertTrue(mock_daemon.return_value.start.called)
            self.assertFalse(mock_daemon.return_value.restart.called)
            self.assertFalse(mock_daemon.return_value.stop.called)

        with patch('client.client.ClientDaemon') as mock_daemon:
            client.call_daemon(c, 'stop')
            self.assertTrue(mock_daemon.called)
            self.assertFalse(mock_daemon.return_value.start.called)
            self.assertFalse(mock_daemon.return_value.restart.called)
            self.assertTrue(mock_daemon.return_value.stop.called)

        with patch('client.client.ClientDaemon') as mock_daemon:
            client.call_daemon(c, 'restart')
            self.assertTrue(mock_daemon.called)
            self.assertFalse(mock_daemon.return_value.start.called)
            self.assertTrue(mock_daemon.return_value.restart.called)
            self.assertFalse(mock_daemon.return_value.stop.called)

    @patch.object(client, 'call_daemon')
    @patch.object(BaseClient.BaseClient, 'run')
    def test_main(self, mock_run, mock_client):
        mock_client.return_value = None
        mock_run.return_value = None
        # this is a bit harder to test. Just try to get some coverage
        args = ['--url', 'testUrl', '--build-key', '123', '--configs', 'config', 'config1', '--name', 'name', '--single-shot']
        client.main(args)
        daemon_args = args + ['--daemon', 'start']
        client.main(daemon_args)
