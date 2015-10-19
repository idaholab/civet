#!/usr/bin/env python
from client import Client, InterruptHandler
import os, sys, argparse
import time, traceback, socket
from daemon import Daemon

if os.environ.has_key('MODULESHOME'):
  sys.path.append(os.getenv('MODULESHOME') + '/init')
  from python import module as modulecmd
else:
  print('No module environment detected')
  sys.exit(1)

# First arg is full server, ie https://localhost
# Second is the build_key
# Third is an optional pathname to the certificate of the server.
# When False, SSL cert verification will not be done.
SERVERS = [('server0', 'build_key', False), ]

CONFIG_MODULES = {'linux-gnu': 'moose-dev-gcc',
    'linux-clang': 'moose-dev-clang',
    'linux-valgrind': 'moose-dev-gcc',
    'linux-gnu-coverage': 'moose-dev-gcc',
    'linux-intel': 'moose-dev-intel',
    'linux-gnu-timing': 'moose-dev-gcc',
    }


class INLClient(Client):
  """
  The INL version of the build client.
  Loads the appropiate environment based
  on the build config
  """
  """
  def __init__(self, **kwds):
    super(INLClient, self).__init__(**kwds)
  """

  def run(self, single=False):
    """
    Main client loop. Polls the server for jobs and runs them.
    Loads the proper environment for each config.
    """
    self.logger.info('Starting {} with MOOSE_JOBS={}'.format(self.name, os.environ['MOOSE_JOBS']))
    self.logger.info('Build root: {}'.format(os.environ['BUILD_ROOT']))
    # do this here in case we are in daemon mode. The signal handler
    # needs to be setup in this process
    self.sighandler = InterruptHandler()
    self.configs = CONFIG_MODULES.keys()
    while True:
      ran_job = False
      for server in SERVERS:
        if self.sighandler.interrupted:
          break
        self.logger.debug('Trying {}'.format(server[0]))
        self.verify = server[2]
        self.url = server[0]
        self.build_key = server[1]
        try:
          reply = self.find_job()
          if reply and reply.get('success'):
            modulecmd('purge')
            modulecmd('load', CONFIG_MODULES[reply['config']])
            self.run_job(reply['job_info'])
            ran_job = True
        except Exception as e:
          self.logger.debug("Error: %s" % traceback.format_exc(e))

      if self.sighandler.interrupted:
        self.logger.info("Received signal...exiting")
        break
      if single:
        break
      if not ran_job:
        time.sleep(self.poll)

def commandline_client(args):
  parser = argparse.ArgumentParser()
  parser.add_argument(
      '--num-jobs',
      dest='num_jobs',
      default='2',
      help='Determines how many processors this client will use.',
      required=True)
  parser.add_argument(
      '--client',
      dest='client',
      help='The number of the client.',
      required=True)
  parser.add_argument(
      '--daemon',
      dest='daemon',
      choices=['start', 'stop', 'restart'],
      help="Start a UNIX daemon.",
      required=True)

  parsed = parser.parse_args(args)
  jobs = parsed.num_jobs
  os.environ['MOOSE_JOBS'] = jobs
  os.environ['JOBS'] = jobs
  os.environ['RUNJOBS'] = jobs
  os.environ['LOAD'] = jobs
  build_root = '{}/civet/client_root_{}'.format(os.environ['HOME'], parsed.client)
  os.environ['BUILD_ROOT'] = build_root

  log_dir = '{}/civet/logs'.format(os.environ['HOME'])
  client_name = '{}_{}'.format(socket.gethostname(), parsed.client)
  c = INLClient(
      name=client_name,
      log_dir=log_dir,
      build_key='',
      url='',
      configs='',
      verify=False,
      )
  return c, parsed.daemon

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
      print('started')

def main(args):
  client, daemon_cmd = commandline_client(args)
  call_daemon(client, daemon_cmd)

if __name__ == "__main__":
  main(sys.argv[1:])
