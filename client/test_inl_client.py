from django.test import SimpleTestCase
import inl_client
import time, os, shutil, tempfile
from mock import patch

class INLClientTestCase(SimpleTestCase):
  def setUp(self):
    self.log_dir = tempfile.mkdtemp()
    os.environ['HOME'] = self.log_dir
    base_dir = '{}/civet'.format(self.log_dir)
    os.mkdir(base_dir)
    base_dir += '/logs'
    os.mkdir(base_dir)

  def tearDown(self):
    shutil.rmtree(self.log_dir)


  class ResponseTest(object):
    def __init__(self, in_json, do_raise=False, status_code=200):
      self.in_json = in_json
      self.do_raise = do_raise
      self.status_code = status_code
    def json(self):
      return self.in_json
    def raise_for_status(self):
      if self.do_raise:
        raise Exception("Bad response status code")

  def create_client(self, args):
    c, cmd = inl_client.commandline_client(args)
    return c, cmd

  def create_json_response(self, canceled=False, success=True):
    ret = {'status': 'OK'}
    if canceled:
      ret['command'] = 'cancel'
    else:
      ret['command'] = 'none'
    ret['success'] = success
    return ret

  def create_step(self, t=2, num=1):
    step = {'environment': {'foo': 'bar'},
        'script': 'echo test_output1; sleep %s; echo test_output2' % t,
        'stepresult_id': 1,
        'step_num': num,
        'name': 'step {}'.format(num),
        'step_id': num,
        'abort_on_failure': True,
        }
    return step

  @patch.object(inl_client.Client, 'find_job')
  @patch.object(inl_client.Client, 'run_job')
  @patch.object(time, 'sleep')
  def test_run(self, mock_sleep, mock_run_job, mock_find_job):
    reply = {'success': True, 'job_info': {}}
    mock_find_job.return_value = reply
    mock_run_job.return_value = True
    args = ['--max-clients', '2', '--client', '0', '--daemon', 'stop',]
    c, cmd = self.create_client(args)
    c.log_file = '/tmp/civet_test/log.txt'
    c.run(single=True)

    reply['success'] = False
    c.run(single=True)

    mock_find_job.side_effect = Exception
    c.run(single=True)

    with self.assertRaises(Exception):
      mock_sleep.side_effect = Exception
      c.run(single=False)

  def test_commandline_client(self):
    args = []
    with self.assertRaises(SystemExit):
      c, cmd = inl_client.commandline_client(args)

    # make sure it exits unless all required
    # arguments are passed in
    args.extend(['--max-clients', '2'])
    print(args)
    with self.assertRaises(SystemExit):
      c, cmd = inl_client.commandline_client(args)

    args.extend(['--client', '0'])
    with self.assertRaises(SystemExit):
      c, cmd = inl_client.commandline_client(args)

    # this is the last required arg
    args.extend(['--daemon', 'stop'])
    c, cmd = inl_client.commandline_client(args)
    self.assertEqual(cmd, 'stop')

  def test_call_daemon(self):
    args = ['--max-clients', '2', '--client', '0', '--daemon', 'stop',]
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
    args = ['--max-clients', '2', '--client', '0', '--daemon', 'stop',]
    inl_client.main(args)

  def test_module(self):
    # just test when MODULESHOME is not set
    with self.assertRaises(SystemExit):
      del os.environ['MODULESHOME']
      reload(inl_client)
