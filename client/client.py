#!/usr/bin/env python
import logging
import argparse
import os, sys, signal
import requests
import time
import json
import subprocess
import tempfile
import traceback
import select
from daemon import Daemon

class JobCancelException(Exception):
  pass

class ClientException(Exception):
  pass

class ServerException(Exception):
  pass

class BadRequestException(Exception):
  pass

class InterruptHandler(object):
  def __init__(self, sig=[signal.SIGINT, signal.SIGTERM, signal.SIGHUP]):
    self.sig = sig
    self.interrupted = False

    self.orig_handler = {}
    for sig in self.sig:
      self.orig_handler[sig] = signal.getsignal(sig)

    def handler(signum, sigframe):
      self.interrupted = True

    for sig in self.sig:
      signal.signal(sig, handler)

  def __exit__(self, type, value, tb):
    for sig in self.sig:
      signal.signal(sig, self.original_handler[sig])

class Client(object):
  """
  This is the job server client. It polls the server
  for new jobs, requests one, and then runs it.
  While running a job it reports back with output
  from the job. During this operation the server
  can respond with commands to the the client. Mainly
  to cancel the job.
  """
  def __init__(self,
      name,
      build_key,
      configs,
      url,
      single_shot = True,
      poll = 30,
      log_dir = ".",
      log_file = None,
      max_retries = 10,
      verify = True,
      time_between_retries = 10,
      update_result_time = 10,
      ssl_cert = None,
      ):

    self.url = url
    self.build_key = build_key
    self.configs = configs
    self.name = name
    self.single_shot = single_shot
    self.poll = poll
    self.max_retries = max_retries
    self.verify = verify
    self.log_file = None
    self.set_log_dir(log_dir)
    self.set_log_file(log_file)
    self.time_between_retries = time_between_retries
    self.update_result_time = update_result_time

    if not self.log_file:
      raise ClientException('Log file not set')

    formatter = logging.Formatter('%(asctime)-15s:%(levelname)s:%(message)s')
    fhandler = logging.FileHandler(self.log_file)
    fhandler.setFormatter(formatter)
    self.logger = logging.getLogger(__name__)
    self.logger.addHandler(fhandler)
    self.logger.setLevel(logging.DEBUG)
    self.sighandler = InterruptHandler()
    if ssl_cert:
      self.verify = ssl_cert

  def set_log_dir(self, log_dir):
    """
    Sets the log dir. If log_dir is set
    the log file name will have a set name of
    "civet_client_<name>_<pid>.log"
    raises ClientException if the directory doesn't
    exist or isn't writable.
    """
    if not log_dir:
      return

    log_dir = os.path.abspath(log_dir)
    self.check_log_dir(log_dir)
    self.log_file = "%s/civet_client_%s.log" % (log_dir, self.name)

  def check_log_dir(self, log_dir):
    """
    Makes sure the log directory exists and is writable
    """
    if not os.path.isdir(log_dir):
      raise ClientException('Log directory (%s) does not exist!' % log_dir)

    if not os.access(log_dir, os.W_OK):
      raise ClientException('Log directory (%s) is not writeable!' % log_dir)

  def set_log_file(self, log_file):
    """
    Specify a log file to use.
    raises ClientException if the directory doesn't
    exist or isn't writable.
    """
    if not log_file:
      return

    log_file = os.path.abspath(log_file)

    log_dir = os.path.dirname(log_file)
    self.check_log_dir(log_dir)
    self.log_file = log_file

  def get_possible_jobs(self):
    """
    Request a list of jobs from the server.
    Returns a dict of the jobs.
    It will retry a set number of times before failing.
    Get the url and return a dict with the JSON, retrying until it works """
    job_url = self.get_job_url()

    self.logger.debug('Trying to get jobs at {}'.format(job_url))
    err_str = ''
    for i in xrange(self.max_retries):
      if self.sighandler.interrupted:
        err_str = 'Signal received'
        break
      try:
        response = requests.get(job_url, verify=self.verify)
        data = response.json()
        if 'jobs' not in data:
          err_str = 'While retrieving jobs, server gave invalid JSON : %s' % data
          self.logger.error(err_str)
          raise ServerException(err_str)
        return data['jobs']
      except ServerException:
        raise
      except Exception as e:
        self.logger.warning(
            'Failed (%s/%s) to retrieve jobs at %s. Error: %s' %
              ( i+1, self.max_retries, job_url, traceback.format_exc(e)))
        if i < (self.max_retries-1):
          time.sleep(self.time_between_retries)

    if not err_str:
      err_str = 'Max retries reached when fetching %s' % job_url
    self.logger.warning(err_str)
    raise ServerException(err_str)

  def post_json(self, request_url, data):
    """
    Post the supplied dict holding JSON data to the url and return a dict
    with the JSON, retrying until it works
    """
    err_str = ''
    bad_request = False
    self.logger.debug('Posting to {}'.format(request_url))
    for i in xrange(self.max_retries):
      reply = {}
      try:
        #always include the name so the server can keep track
        data['client_name'] = self.name
        in_json = json.dumps(data, separators=(',', ': '))
        response = requests.post(request_url, in_json, verify=self.verify)
        if response.status_code == 400:
          # shouldn't retry on BAD REQUEST.
          # this can happen, for example, when 2 clients
          # try to claim the same job. The loser will get a bad request.
          # It can also happen if a job gets invalidated while
          # running.
          err_str = 'Made a bad request. No retries'
          bad_request = True
          self.logger.warning(err_str)
          break

        # other bad codes are errors and we will retry
        response.raise_for_status()
        reply = response.json()
      except Exception as e:
        self.logger.warning(
            'Failed (%s/%s) to POST at %s.\nMessage: %s\nError: %s' %
              (i, self.max_retries, request_url, e, traceback.format_exc(e)))
        if i < (self.max_retries-1):
          time.sleep(self.time_between_retries)
          continue

      if 'status' not in reply:
        err_str = 'While posting to %s, server gave invalid JSON : %s' % (request_url, reply)
        self.logger.error(err_str)
        raise ServerException(err_str)
      elif reply['status'] != 'OK':
        err_str = 'While posting to %s, an error occured on the server: %s' % (request_url, reply)
        self.logger.error(err_str)
        raise ServerException(err_str)
      else:
        return reply

    if not err_str:
      err_str = 'Max retries reached when fetching %s' % request_url

    self.logger.warning(err_str)
    if bad_request:
      raise BadRequestException(err_str)

    raise ServerException(err_str)

  def get_job_url(self):
    return "%s/client/ready_jobs/%s/%s/" % (self.url, self.build_key, self.name)

  def get_start_step_result_url(self, stepresult_id):
    return "%s/client/start_step_result/%s/%s/%s/" % (self.url, self.build_key, self.name, stepresult_id)

  def get_complete_step_result_url(self, stepresult_id):
    return "%s/client/complete_step_result/%s/%s/%s/" % (self.url, self.build_key, self.name, stepresult_id)

  def get_update_step_result_url(self, stepresult_id):
    return "%s/client/update_step_result/%s/%s/%s/" % (self.url, self.build_key, self.name, stepresult_id)

  def get_job_finished_url(self, job_id):
    return "%s/client/job_finished/%s/%s/%s/" % (self.url, self.build_key, self.name, job_id)

  def get_claim_job_url(self, config):
    return "%s/client/claim_job/%s/%s/%s/" % (self.url, self.build_key, config, self.name)

  def claim_job(self, jobs):
    """
    We have a list of jobs from the server. Now try
    to claim one that matches our config so that
    other clients won't run it.
    """
    self.logger.debug("Checking %s jobs to claim" % len(jobs))
    for job in jobs:
      config = job['config']
      if config not in self.configs:
        self.logger.debug("Incomptable config %s : Known configs : %s" % (config, self.configs))
        continue

      claim_json = {
        'job_id': job['id'],
        'config': config,
        'client_name': self.name
      }

      try:
        claim = self.post_json(self.get_claim_job_url(config), claim_json)
        if claim.get('success'):
          self.logger.debug("Claimed job config %s on recipe %s" % (config, claim['job_info']['recipe_name']))
          return claim
        else:
          self.logger.debug("Failed to claim job config %s on recipe %s. Response: %s" % (config, job['id'], claim))
      except Exception as e:
        self.logger.warning('Tried and failed to claim job %s. Error: %s' % (job['id'], traceback.format_exc(e.message)))

    self.logger.info('No jobs to run')
    return None

  def run_job(self, job):
    """
    We have claimed a job, now run it.
    """

    env = os.environ.copy()

    # copy top level recipe settings to the environ
    for pairs in job['environment']:
      env[pairs[0]] = str(pairs[1])

    # concatenate all the pre-step sources into
    # one. This will be used as the BASH_ENV
    # when executing the command.
    final_pre_step_sources = ''
    for pre_step_source in job['prestep_sources']:
      final_pre_step_sources += '{}\n'.format(pre_step_source.replace('\r', ''))

    pre_step_source = tempfile.NamedTemporaryFile(delete=False)
    pre_step_source.write(final_pre_step_sources)
    pre_step_source.close()
    env['BASH_ENV'] = pre_step_source.name
    self.logger.info('BASE_ENV={}'.format(pre_step_source.name))

    job_start_time = time.time()

    job_data = {'canceled': False, 'failed': False}
    steps = job['steps']

    self.logger.info('Starting job %s on %s on server %s' % (job['recipe_name'], env['base_repo'], self.url))

    for step in steps:
      results = self.run_step(job['job_id'], step, env)

      if results['canceled']:
        job_data['canceled'] = True
        break

      if results['exit_status'] != 0 and job['abort_on_failure'] and step['step_abort_on_failure']:
        job_data['failed'] = True
        self.logger.info('Step failed. Stopping')
        break

    job_data['seconds'] = int(time.time() - job_start_time) #would be float
    job_data['complete'] = True
    job_data['client_name'] = self.name
    try:
      self.post_json(self.get_job_finished_url(job['job_id']), job_data)
    except Exception as e:
        self.logger.error('Cannot set final job status. Error: %s' % e.message)

    self.logger.info('Finished Job %s' % job['recipe_name'])
    os.remove(pre_step_source.name)
    return job_data

  def update_step(self, url, step, chunk_data):
    reply = None
    try:
      reply = self.post_json(url, chunk_data)
    except BadRequestException as e:
      err_str = 'Received a bad request, job canceled'
      self.logger.info(err_str)
      raise JobCancelException(err_str)
    except Exception as e:
      self.logger.error('Failed to update step result for step %s. Error : %s' % (step['step_num'], e.message))
      return False

    if reply.get('command') == 'cancel':
      err_str = 'Received cancel while running step %s' % step['step_num']
      self.logger.info(err_str)
      raise JobCancelException(err_str)
    return True

  def read_process_output(self, proc, step, step_data):
    """
    This reads the output of a process and
    periodically reports it back to the server.
    """
    out = []
    chunk_out = []
    start_time = time.time()
    chunk_start_time = time.time()
    url = self.get_update_step_result_url(step['stepresult_id'])

    while True:
      if self.sighandler.interrupted:
        raise JobCancelException('Recieved signal')

      reads = [proc.stdout.fileno(),]
      ret = select.select(reads, [], [], 1)
      for fd in ret[0]:
        if fd == proc.stdout.fileno():
          line = proc.stdout.readline()
          out.append(line)
          chunk_out.append(line)

      diff = time.time() - chunk_start_time
      if diff > self.update_result_time: # Report some output every x seconds
        step_data['output'] = "".join(chunk_out)
        step_data['time'] = int(time.time() - start_time) #would be float
        if self.update_step(url, step, step_data):
          chunk_out = []

        chunk_start_time = time.time()

      if proc.poll() != None:
        break

    # we might not have gotten everything, the
    # rest is in communicate()[0]
    out.append(proc.communicate()[0])
    step_data['output'] = ''.join(out)
    step_data['complete'] = True
    step_data['time'] = int(time.time() - start_time) #would be float
    return step_data

  def kill_job(self, proc):
    """
    If the job gets cancelled then we need to
    kill the running job.
    Try to kill -15  it first to let it shutdown
    gracefully. If not, then kill -9 it until it is
    dead.
    """
    try:
      proc.terminate()
      for i in xrange(5): # just try a few times to absolutely kill it
        if proc.poll() != None:
          break

        self.logger.warning("Trying to forcefully kill %s" % proc.pid)
        proc.kill()
        time.sleep(1)

      if proc.poll() == None:
        self.logger.warning("Unable to kill process %s." % proc.pid)
      else:
        self.logger.warning("%s killed as requested." % proc.pid)
    except OSError:
      pass # this will be due to trying to kill a process that is already dead

  def run_step(self, job_id, step, env):
    """
    Runs one of the steps of the job.
    """

    step_data = {
      'job_id': job_id,
      'step_id': step['step_id'],
      'client_name': self.name,
      'stepresult_id': step['stepresult_id'],
      'step_num': step['step_num'],
      'client_name': self.name,
      'output': None,
      'exit_status': 0,
      'complete': False,
      'time': 0,
      }

    self.logger.info('Starting step %s' % step['step_name'])

    url = self.get_start_step_result_url(step['stepresult_id'])
    self.update_step(url, step, step_data)

    # copy the env so we don't pollute the global env
    step_env = env.copy()
    for pairs in step['environment']:
      step_env[pairs[0]] = str(pairs[1])

    step_env['step_position'] = str(step['step_num'])
    step_env['step_name'] = step['step_name']
    proc = subprocess.Popen(
        step['script'].replace('\r', ''),
        shell=True,
        env=step_env,
        executable='/bin/bash',
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        )

    step_start = time.time()
    try:
      step_data = self.read_process_output(proc, step, step_data)
      proc.wait() # To get the returncode set
      step_data['canceled'] = False
    except Exception:
      self.kill_job(proc)
      step_data['canceled'] = True
      step_data['output'] = ''

    step_data['exit_status'] = proc.returncode
    step_data['time'] = int(time.time() - step_start) #would be float

    url = self.get_complete_step_result_url(step['stepresult_id'])
    self.update_step(url, step, step_data)
    return step_data

  def find_job(self):
    """
    Tries to find and claim a job to run.
    """
    jobs = None
    try:
      jobs = self.get_possible_jobs()
      self.logger.debug('Found {} possible jobs  at {}'.format(len(jobs), self.url))
    except Exception as e:
      err_str = "Can't get possible jobs. Check URL.\nError: {}".format(e)
      self.logger.error(err_str)
      raise ServerException(err_str)

    if jobs:
      job = self.claim_job(jobs)
      return job
    return None

  def run(self):
    """
    Main client loop. Polls the server for jobs
    and runs them.
    """

    # do this here in case we are in daemon mode. The signal handler
    # needs to be setup in this process
    self.sighandler = InterruptHandler()
    while True:
      do_poll = True
      try:
        reply = self.find_job()
        if reply and reply.get('success'):
          self.run_job(reply['job_info'])
          # finished the job, look for a new one immediately
          do_poll = False
        else:
          self.logger.debug('No available jobs. Response: %s' % reply)
      except Exception as e:
        self.logger.debug("Error: %s" % traceback.format_exc(e))

      if self.sighandler.interrupted:
        self.logger.info("Received signal...exiting")
        break
      if self.single_shot:
        break

      if do_poll:
        time.sleep(self.poll)

class ClientDaemon(Daemon):
  def run(self):
    self.client.run()
  def set_client(self, client):
    self.client = client

def call_daemon(client, cmd):
    pfile = '/tmp/client_%s.pid' % client.name
    client_daemon = ClientDaemon(pfile, stdout=client.log_file, stderr=client.log_file)
    client_daemon.set_client(client)
    if cmd == 'restart':
      client_daemon.restart()
    elif cmd == 'stop':
      client_daemon.stop()
    elif cmd == 'start':
      client_daemon.start()

def commandline_client(args):
  parser = argparse.ArgumentParser()
  parser.add_argument(
      "--url",
      dest='url',
      help="The URL of the CIVET site.",
      required=True)
  parser.add_argument(
      "--build-key",
      dest='build_key',
      help="Your build_key",
      required=True)
  parser.add_argument(
      "--configs",
      dest='configs',
      nargs='+',
      help="The configurations this client supports (eg 'linux-gnu')",
      required=True)
  parser.add_argument(
      "--name",
      dest='name',
      help="The name for this particular client. Should be unique.",
      required=True)
  parser.add_argument(
      "--single-shot",
      dest='single_shot',
      action='store_true',
      help="Execute one test (if there is one) and then exit")
  parser.add_argument(
      "--poll",
      dest='poll',
      type=int,
      default=30,
      help="Number of seconds to wait before polling for more jobs in continuous mode")
  parser.add_argument(
      "--daemon",
      dest='daemon',
      choices=['start', 'stop', 'restart'],
      help="Start a UNIX daemon.")
  parser.add_argument(
      "--log-dir",
      dest='log_dir',
      default='.',
      help="Where to write the log file.  The log will be written as ci_PID.log")
  parser.add_argument(
      "--log-file",
      dest='log_file',
      help="Filename to append the log to")
  parser.add_argument(
      "--max-retries",
      dest='max_retries',
      type=int,
      default=10,
      help="Number of times to retry a connection attempt")
  parser.add_argument(
      "--insecure",
      dest='insecure',
      action='store_false',
      help="Turns off SSL certificate verification")
  parser.add_argument(
      "--ssl-cert",
      dest='ssl_cert',
      help="An crt file to be used when doing SSL certificate verification. This will override --insecure.")
  #parsed, unknown = parser.parse_known_args(args)
  parsed = parser.parse_args(args)

  return Client(
      name=parsed.name,
      build_key=parsed.build_key,
      configs=parsed.configs,
      url=parsed.url,
      single_shot=parsed.single_shot,
      poll=parsed.poll,
      log_dir=parsed.log_dir,
      log_file=parsed.log_file,
      max_retries=parsed.max_retries,
      verify=parsed.insecure,
      ssl_cert=parsed.ssl_cert,
      ), parsed.daemon

def main(args):
  client, daemon_cmd = commandline_client(args)
  if daemon_cmd:
    call_daemon(client, daemon_cmd)
  else:
    # set up logging to console
    console = logging.StreamHandler()
    formatter = logging.Formatter('%(asctime)-15s:%(levelname)s:%(message)s')
    console.setFormatter(formatter)
    client.logger.addHandler(console)
    client.run()

if __name__ == "__main__":
  main(sys.argv[1:])

