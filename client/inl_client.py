#!/usr/bin/env python
import os, sys, argparse
import socket
import INLClient
from daemon import Daemon

def commandline_client(args):
  parser = argparse.ArgumentParser()
  parser.add_argument('--num-jobs', dest='num_jobs', type=int, default=2, help='Determines how many processors this client will use.', required=True)
  parser.add_argument('--client', dest='client', type=int, help='The number of the client.', required=True)
  parser.add_argument('--daemon', dest='daemon', choices=['start', 'stop', 'restart'], help="Start a UNIX daemon.", required=True)

  parsed = parser.parse_args(args)
  jobs = parsed.num_jobs
  os.environ['MOOSE_JOBS'] = str(jobs)
  os.environ['JOBS'] = str(jobs)
  os.environ['RUNJOBS'] = str(jobs)
  os.environ['LOAD'] = str(jobs)
  build_root = '{}/civet/client_root_{}'.format(os.environ['HOME'], parsed.client)
  os.environ['BUILD_ROOT'] = build_root

  log_dir = '{}/civet/logs'.format(os.environ['HOME'])
  client_name = '{}_{}'.format(socket.gethostname(), parsed.client)
  client_info = {"url": "",
      "client_name": client_name,
      "server": "",
      "servers": [],
      "configs": [],
      "ssl_verify": False,
      "ssl_cert": "",
      "log_file": "",
      "log_dir": log_dir,
      "build_key": "",
      "single_shot": False,
      "poll": 30,
      "daemon_cmd": parsed.daemon,
      "request_timeout": 30,
      "update_step_time": 20,
      "server_update_timeout": 5,
      # This needs to be bigger than update_step_time so that
      # the ping message doesn't become the default message
      "server_update_interval": 40,
      }

  c = INLClient.INLClient(client_info)
  return c, parsed.daemon

class ClientDaemon(Daemon):
  def run(self):
    self.client.run()
  def set_client(self, client):
    self.client = client

def call_daemon(client, cmd):
    pfile = '/tmp/client_%s.pid' % client.client_info["client_name"]
    client_daemon = ClientDaemon(pfile, stdout=client.client_info["log_file"], stderr=client.client_info["log_file"])
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
