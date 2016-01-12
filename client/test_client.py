from django.test import SimpleTestCase
import requests
import client
import time, os
from mock import patch
import subprocess
import logging, sys


def start_logger():
  """
  This is to allow for the various loggers
  to actually output the logs to the
  testing stdout. Not on by default
  because it gets messy.
  """
  logger = logging.getLogger()
  logger.level = logging.DEBUG
  stream_handler = logging.StreamHandler(sys.stdout)
  logger.addHandler(stream_handler)

#start_logger()

class ClientTestCase(SimpleTestCase):

  def create_client(self,
      name="testClient",
      build_key="1234",
      configs=["test_config",],
      url="url",
      single_shot=True,
      poll=30,
      log_dir=".",
      log_file=None,
      max_retries=1,
      verify=True,
      time_between_retries=0,
      ):
    return client.Client(name, build_key, configs, url, single_shot,
        poll, log_dir, log_file, max_retries, verify)

  def test_log_dir(self):
    c = self.create_client()
    self.assertEqual("testClient", c.name)
    self.assertIn(c.name, c.log_file)
    with self.assertRaises(client.ClientException):
      self.create_client(log_dir="/var")
    with self.assertRaises(client.ClientException):
      self.create_client(log_dir="/var/aafafafaf")
    with self.assertRaises(client.ClientException):
      self.create_client(log_dir=None, log_file=None)

  def test_log_file(self):
    c = self.create_client(log_file="test_log")
    self.assertIn('test_log', c.log_file)

    with self.assertRaises(client.ClientException):
      self.create_client(log_file="/var/foo")
    with self.assertRaises(client.ClientException):
      self.create_client(log_file="/aafafafaf/fo")

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

  @patch.object(requests, 'get')
  def test_get_possible_jobs(self, mock_get):
    # test the non error operation
    mock_get.return_value = self.ResponseTest({'jobs':None})
    c = self.create_client()
    jobs = c.get_possible_jobs()
    c.time_between_retries = 0
    self.assertEqual(jobs, mock_get.return_value.json()['jobs'])

    #check when the server responds incorrectly
    with self.assertRaises(client.ServerException):
      mock_get.return_value = self.ResponseTest({})
      c.get_possible_jobs()

    c.max_retries = 2
    #check when requests throws and we hit retries
    with self.assertRaises(client.ServerException):
      mock_get.side_effect = Exception
      c.get_possible_jobs()

  @patch.object(requests, 'post')
  def test_post_json(self, mock_post):
    in_data = {'foo': 'bar'}
    out_data = self.create_json_response()
    url = 'foo'
    # test the non error operation
    mock_post.return_value = self.ResponseTest(out_data)
    c = self.create_client()
    ret = c.post_json(url, in_data)
    c.time_between_retries = 0
    c.max_retries = 2
    self.assertEqual(ret, mock_post.return_value.json())

    #check when the server responds incorrectly
    with self.assertRaises(client.ServerException):
      mock_post.return_value = self.ResponseTest({})
      c.post_json(url, in_data)

    #check when response gives error
    with self.assertRaises(client.ServerException):
      mock_post.return_value = self.ResponseTest({'status': 'error'})
      c.post_json(url, in_data)

    #check when the server recieves a bad request
    with self.assertRaises(client.BadRequestException):
      mock_post.return_value = self.ResponseTest({'status': 'error'}, status_code=400)
      c.post_json('badrequest', in_data)

    c.max_retries = 0
    #check when requests throws and we hit retries
    with self.assertRaises(client.ServerException):
      mock_post.side_effect = Exception()
      c.post_json(url, in_data)


  @patch.object(client.Client, 'post_json')
  def test_claim_job(self, mock_post_json):
    c = self.create_client()
    jobs = [{'config':c.configs[0], 'id':1},]
    jobs_bad = [{'config':'bad_config', 'id':1},]
    out_data = self.create_json_response()
    out_bad_data = self.create_json_response(success=False)
    out_data['job_info'] = {'recipe_name': 'test'}
    mock_post_json.return_value = out_data
    c.time_between_retries = 0
    # successfull operation
    ret = c.claim_job(jobs)
    self.assertEqual(ret, out_data)

    # unsuccessfull operation
    mock_post_json.return_value = out_bad_data
    ret = c.claim_job(jobs)
    self.assertEqual(ret, None)

    # try when we don't have a matching config
    mock_post_json.return_value = out_data
    ret = c.claim_job(jobs_bad)
    self.assertEqual(ret, None)

    # try when server problems
    mock_post_json.side_effect = Exception
    ret = c.claim_job(jobs)
    self.assertEqual(ret, None)

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
        'step_name': 'step {}'.format(num),
        'step_id': num,
        'step_abort_on_failure': True,
        'step_allowed_to_fail': False,
        }
    return step

  @patch.object(requests, 'post')
  @patch.object(client.Client, 'run_step')
  def test_run_job(self, mock_run_step, mock_post):
    c = self.create_client()
    c.update_result_time = 1
    job = {'environment':[('base_repo', 'base repo'),],
      'recipe_name': 'test_job',
      'prestep_sources': 'prestep',
      'abort_on_failure': True,
      'job_id': 1,
      'step_id': 1,
      'stepresult_id': 1,
      'steps':[self.create_step(num=1), self.create_step(num=2)]}

    repl = self.create_json_response()
    mock_post.return_value = self.ResponseTest(repl)
    run_step_results = {'canceled': False, 'next_step': True, 'exit_status': 0}
    mock_run_step.return_value = run_step_results

    results = c.run_job(job)
    self.assertEqual(results['complete'], True)
    self.assertEqual(results['canceled'], False)
    self.assertIn('seconds', results)
    self.assertIn('client_name', results)

    # test bad exit_status
    run_step_results['next_step'] = False
    run_step_results['exit_status'] = 1
    mock_run_step.return_value = run_step_results

    results = c.run_job(job)
    self.assertEqual(results['complete'], True)
    self.assertEqual(results['canceled'], False)
    self.assertTrue(results.get('failed'))
    self.assertIn('seconds', results)
    self.assertIn('client_name', results)

    # test bad exit_status but server says it is OK
    run_step_results['next_step'] = True
    run_step_results['exit_status'] = 1
    mock_run_step.return_value = run_step_results

    results = c.run_job(job)
    self.assertEqual(results['complete'], True)
    self.assertEqual(results['canceled'], False)
    self.assertFalse(results.get('failed'))
    self.assertIn('seconds', results)
    self.assertIn('client_name', results)

    # test canceled
    run_step_results['canceled'] = True
    mock_run_step.return_value = run_step_results

    results = c.run_job(job)
    self.assertEqual(results['complete'], True)
    self.assertEqual(results['canceled'], True)
    self.assertIn('seconds', results)
    self.assertIn('client_name', results)

    # test server down, can't post

    mock_post.side_effect = Exception
    results = c.run_job(job)
    self.assertEqual(results['complete'], True)
    self.assertEqual(results['canceled'], True)
    self.assertIn('seconds', results)
    self.assertIn('client_name', results)

  @patch.object(client.Client, 'post_json')
  def test_update_step(self, mock_post_json):
    repl = {'command': 'none'}
    c = self.create_client()
    url = c.get_update_step_result_url(1)
    mock_post_json.return_value = repl
    step = {'step_num': 1, 'stepresult_id': 1}
    chunk_data = {}
    ret = c.update_step(url, step, chunk_data)
    self.assertTrue(ret)
    self.assertTrue(chunk_data['next_step'])

    chunk_data.pop('next_step', None)
    repl['next_step'] = False
    mock_post_json.return_value = repl
    ret = c.update_step(url, step, chunk_data)
    self.assertTrue(ret)
    self.assertFalse(chunk_data['next_step'])

    repl['command'] = 'cancel'
    repl['next_step'] = True
    chunk_data.pop('next_step', None)
    mock_post_json.return_value = repl
    with self.assertRaises(client.JobCancelException):
      ret = c.update_step(url, step, chunk_data)

    mock_post_json.side_effect = Exception
    chunk_data.pop('next_step', None)
    ret = c.update_step(url, step, chunk_data)
    self.assertFalse(ret)
    self.assertTrue(chunk_data['next_step'])

    mock_post_json.side_effect = client.BadRequestException()
    with self.assertRaises(client.JobCancelException):
      ret = c.update_step(url, step, chunk_data)

  @patch.object(requests, 'post')
  def test_read_process_output(self, mock_post):
    c = self.create_client()
    c.update_result_time = 1
    repl = self.create_json_response()
    cancel = self.create_json_response(canceled=True)
    step = self.create_step()
    script = "for i in $(seq 5);do echo output $i; sleep 1; done"
    proc = subprocess.Popen(
        script,
        shell=True,
        executable='/bin/bash',
        stdout=subprocess.PIPE
        )
    mock_post.return_value = self.ResponseTest(repl)
    out = c.read_process_output(proc, step, {})
    self.assertIn('5', out['output'])
    proc.wait()

    proc = subprocess.Popen(
        script,
        shell=True,
        executable='/bin/bash',
        stdout=subprocess.PIPE
        )
    with self.assertRaises(client.JobCancelException):
      mock_post.return_value = self.ResponseTest(cancel)
      url = c.get_update_step_result_url(1)
      c.update_step(url, step, {})
      c.kill_job(proc)
    proc.wait()

    proc = subprocess.Popen(
        script,
        shell=True,
        executable='/bin/bash',
        stdout=subprocess.PIPE
        )

    proc2 = None
    with self.assertRaises(client.JobCancelException):
      mock_post.return_value = self.ResponseTest(repl)
      script2 = 'sleep 2 && kill -USR1 {}'.format(os.getpid())
      proc2 = subprocess.Popen(
        script2,
        shell=True,
        executable='/bin/bash',
        stdout=subprocess.PIPE
        )
      c.read_process_output(proc, step, {})

    proc2.wait()
    proc.wait()
    self.assertTrue(c.cancel_signal.triggered)
    self.assertFalse(c.graceful_signal.triggered)

    proc = subprocess.Popen(
        script,
        shell=True,
        executable='/bin/bash',
        stdout=subprocess.PIPE
        )
    mock_post.return_value = self.ResponseTest(repl)
    c.cancel_signal.triggered = False
    script2 = 'sleep 2 && kill -USR2 {}'.format(os.getpid())
    proc2 = subprocess.Popen(
      script2,
      shell=True,
      executable='/bin/bash',
      stdout=subprocess.PIPE
      )
    c.read_process_output(proc, step, {})

    proc2.wait()
    proc.wait()
    self.assertFalse(c.cancel_signal.triggered)
    self.assertTrue(c.graceful_signal.triggered)


  def test_kill_job(self):
    proc = subprocess.Popen("sleep 30", shell=True, executable='/bin/bash')
    c = self.create_client()
    c.kill_job(proc)
    self.assertEqual(proc.poll(), -15) # SIGTERM


  @patch.object(requests, 'post')
  def test_run_step(self, mock_post):
    c = self.create_client()
    c.update_result_time = 1
    repl = self.create_json_response()
    cancel = self.create_json_response(canceled=True)
    mock_post.return_value = self.ResponseTest(repl)
    step = self.create_step(t=2)

    env = {'step_id': '1', 'stepresult_id': '2'}
    results = c.run_step(1, step, env)
    self.assertIn('test_output1', results['output'])
    self.assertIn('test_output2', results['output'])
    self.assertEqual(results['exit_status'], 0)
    self.assertEqual(results['canceled'], False)

    mock_post.return_value = self.ResponseTest(cancel)
    with self.assertRaises(client.JobCancelException):
      results = c.run_step(1, step, env)
      self.assertEqual(results['canceled'], True)


  @patch.object(client.Client, 'get_possible_jobs')
  @patch.object(client.Client, 'claim_job')
  def test_find_job(self, mock_claim_job, mock_get_possible_jobs):
    mock_claim_job.return_value = "Result"
    mock_get_possible_jobs.return_value = [1]
    c = self.create_client()
    result = c.find_job()
    self.assertEqual(result, mock_claim_job.return_value)

    with self.assertRaises(client.ServerException):
      mock_get_possible_jobs.side_effect = Exception
      result = c.find_job()
      self.assertEqual(result, None)

  @patch.object(client.Client, 'find_job')
  @patch.object(client.Client, 'run_job')
  @patch.object(time, 'sleep')
  def test_run(self, mock_sleep, mock_run_job, mock_find_job):
    reply = {'success': True, 'job_info': {}}
    mock_find_job.return_value = reply
    mock_run_job.return_value = True
    c = self.create_client()
    c.run()

    reply['success'] = False
    c.run()

    mock_find_job.side_effect = Exception
    c.run()

    with self.assertRaises(Exception):
      mock_sleep.side_effect = Exception
      c.single_shot = False
      c.run()

  def test_commandline_client(self):
    args = []
    with self.assertRaises(SystemExit):
      c, cmd = client.commandline_client(args)

    # make sure it exits unless all required
    # arguments are passed in
    args.extend(['--url', 'testUrl'])
    print(args)
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

    self.assertEqual(c.url, 'testUrl')
    self.assertEqual(c.build_key, '123')
    self.assertEqual(c.name, 'testName')
    self.assertEqual(c.configs, ['testConfig', 'testConfig1'])

    args.extend([
        '--single-shot',
        '--poll',
        '1',
        '--log-dir',
        '/tmp',
        '--max-retries',
        '1',
        '--insecure',
        ])

    c, cmd = client.commandline_client(args)
    self.assertTrue(c.single_shot)
    self.assertFalse(c.verify)
    self.assertEqual(c.max_retries, 1)
    self.assertEqual(c.poll, 1)
    self.assertEqual('/tmp', os.path.dirname(c.log_file))

    args.extend([ '--ssl-cert', 'my_cert'])
    args.extend([ '--log-file', '/tmp/testFile'])
    c, cmd = client.commandline_client(args)
    self.assertEqual(c.log_file, '/tmp/testFile')
    self.assertEqual(c.verify, 'my_cert')

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
    c = self.create_client()
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
  @patch.object(client.Client, 'run')
  def test_main(self, mock_run, mock_client):
    mock_client.return_value = None
    mock_run.return_value = None
    args = ['--url', 'testUrl', '--build-key', '123', '--configs', 'config', 'config1', '--name', 'name', '--single-shot']
    client.main(args)
    daemon_args = args + ['--daemon', 'start']
    client.main(daemon_args)
