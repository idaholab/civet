from django.test import SimpleTestCase
from client import client, BaseClient
from . import utils
import os
from mock import patch


class CommandlineClientTests(SimpleTestCase):

  def test_commandline_client(self):
    args = []
    with self.assertRaises(SystemExit):
      c, cmd = client.commandline_client(args)

    # make sure it exits unless all required
    # arguments are passed in
    args.extend(['--url', 'testUrl'])
    with self.assertRaises(SystemExit):
      c, cmd = client.commandline_client(args)

    args.extend(['--build-key', '123'])
    with self.assertRaises(SystemExit):
      c, cmd = client.commandline_client(args)

    args.extend(['--configs', 'testConfig', 'testConfig1'])
    with self.assertRaises(SystemExit):
      c, cmd = client.commandline_client(args)

    # this is the last required arg
    args.extend(['--name', 'testName'])
    c, cmd = client.commandline_client(args)

    self.assertEqual(c.client_info["server"], 'testUrl')
    self.assertEqual(c.client_info["build_key"], '123')
    self.assertEqual(c.client_info["client_name"], 'testName')
    self.assertEqual(c.client_info["build_configs"], ['testConfig', 'testConfig1'])

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

    args.extend([ '--daemon', 'start'])
    c, cmd = client.commandline_client(args)
    self.assertEqual(cmd, 'start')

    args.extend([ '--daemon', 'stop'])
    c, cmd = client.commandline_client(args)
    self.assertEqual(cmd, 'stop')

    args.extend([ '--daemon', 'restart'])
    c, cmd = client.commandline_client(args)
    self.assertEqual(cmd, 'restart')

    args.extend([ '--daemon', 'foo'])
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
