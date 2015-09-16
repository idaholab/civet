#!/usr/bin/env python
from client import Client
import os, sys, multiprocessing, argparse
import time, traceback
import logging
import random

if os.environ.has_key('MODULESHOME'):
  sys.path.append(os.getenv('MODULESHOME') + '/init')
  from python import module as modulecmd
else:
  print('No module environment detected')
  sys.exit(1)

SERVERS = [('server0', 'build_key'), ]

CONFIG_MODULES = {'linux-gnu': 'moose-dev-gcc',
    'linux-clang': 'moose-dev-clang',
    'linux-valgrind': 'moose-dev-gcc',
    'linux-gnu-coverage': 'moose-dev-gcc',
    'linux-intel': 'moose-dev-intel',
    'linux-gnu-timing': 'moose-dev-gcc',
    }


class INLClient(Client):
  def run(self):
    """
    Main client loop. Polls the server for jobs and runs them.
    Loads the proper environment for each config.
    """
    while True:
      ran_job = False
      config_keys = CONFIG_MODULES.keys()
      random.shuffle(config_keys)
      for config in config_keys:
        modulecmd('purge')
        modulecmd('load', CONFIG_MODULES[config])
        random.shuffle(SERVERS)
        for server in SERVERS:
          self.logger.debug('Trying {} {}'.format(server[0], config))
          self.url = server[0]
          self.build_key = server[1]
          self.config = config
          try:
            reply = self.find_job()
            if reply and reply.get('success'):
              self.run_job(reply['job_info'])
              ran_job = True
          except Exception as e:
            self.logger.debug("Error: %s" % traceback.format_exc(e))
      if not ran_job:
        time.sleep(self.poll)

def commandline_client(args):
  parser = argparse.ArgumentParser()
  parser.add_argument(
      '--name',
      dest='name',
      help="The name for this particular client. Should be unique.",
      required=True)
  parser.add_argument(
      '--build-root',
      dest='build_root',
      help="The build root for this client",
      required=True)
  parser.add_argument(
      '--log-dir',
      dest='log_dir',
      default='.',
      help="Where to write the log files.  The log will be written as ci_PID.log",
      required=True)
  parser.add_argument(
      '--max-clients',
      dest='max_clients',
      default='2',
      help='Determines how many processors this client will use.',
      required=True)
  parser.add_argument(
      '--daemon',
      dest='daemon',
      choices=['start', 'stop', 'restart'],
      help="Start a UNIX daemon.")

  parsed = parser.parse_args(args)
  jobs = str((multiprocessing.cpu_count() / 2 / int(parsed.max_clients)))
  os.environ['MOOSE_JOBS'] = jobs
  os.environ['JOBS'] = jobs
  os.environ['RUNJOBS'] = jobs
  os.environ['LOAD'] = jobs
  os.environ['BUILD_ROOT'] = parsed.build_root
  return INLClient(
      name=parsed.name,
      log_dir=parsed.log_dir,
      build_key='',
      url='',
      config='',
      verify=False,
      ), parsed.daemon

def main(args):
  client, daemon_cmd = commandline_client(args)
  console = logging.StreamHandler()
  console.setLevel(logging.DEBUG)
  # set up logging to console
  formatter = logging.Formatter('%(asctime)-15s:%(levelname)s:%(message)s')
  console.setFormatter(formatter)
  logging.getLogger('').addHandler(console)
  client.run()

if __name__ == "__main__":
  main(sys.argv[1:])
