#!/usr/bin/env python

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
import os, sys, argparse, pwd
# Need to add parent directory to the path so that imports work
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
import socket
import platform
import logging, logging.handlers
from client import INLClient, BaseClient
from DaemonLite import DaemonLite

def commandline_client(args):
    parser = argparse.ArgumentParser()
    parser.add_argument('--client', dest='client', type=int, help='The number of the client.', required=True)
    parser.add_argument('--daemon',
            dest='daemon',
            choices=['start', 'stop', 'restart', 'none'],
            help="Start a UNIX daemon.",
            required=True)
    parser.add_argument("--configs",
            dest='configs',
            nargs='+',
            help="The configurations this client supports (eg 'linux-gnu')")
    parser.add_argument("--env",
            dest='env',
            nargs=2,
            action='append',
            help="Sets a client environment variable (example: VAR_NAME VALUE)")
    parser.add_argument("--build-root",
            type=str,
            dest='build_root',
            help="Sets the build root")
    parser.add_argument("--user-client-suffix",
            action='store_true',
            dest='user_client_suffix',
            help='Adds the user to client name as a suffix, i.e, sets the name to <hostname>_<user>_<client number>')


    parsed = parser.parse_args(args)
    home = os.environ.get("CIVET_HOME", os.path.join(os.environ["HOME"], "civet"))

    log_dir = '{}/logs'.format(home)
    client_name = socket.gethostname()
    if parsed.user_client_suffix:
        client_name += '_{}'.format(pwd.getpwuid(os.getuid())[0])
    client_name += '_{}'.format(parsed.client)
    client_info = {"url": "",
        "client_name": client_name,
        "server": "",
        "servers": [],
        "ssl_verify": False,
        "ssl_cert": "",
        "log_file": "",
        "log_dir": log_dir,
        "build_key": "",
        "single_shot": False,
        "poll": 60,
        "daemon_cmd": parsed.daemon,
        "request_timeout": 120,
        "update_step_time": 30,
        "server_update_timeout": 5,
        # This needs to be bigger than update_step_time so that
        # the ping message doesn't become the default message
        "server_update_interval": 50,
        "max_output_size": 5*1024*1024
        }

    c = INLClient.INLClient(client_info)

    # Add a syslog logger
    if platform.system() != 'Windows':
        log_device = '/dev/log' if platform.system() == 'Linux' else '/var/log/syslog'
        syslog_tag = client_name.replace(socket.gethostname() + '_', '')
        syslog_handler = logging.handlers.SysLogHandler(log_device)
        syslog_formatter = logging.Formatter(syslog_tag + ': %(message)s')
        syslog_handler.setFormatter(syslog_formatter)
        syslog_handler.setLevel(logging.INFO)
        logger = logging.getLogger("civet_client")
        logger.addHandler(syslog_handler)

    if parsed.daemon == 'start' or parsed.daemon == 'restart' or platform.system() == "Windows":
        if not parsed.configs:
            raise BaseClient.ClientException('--configs must be provided')

        if parsed.build_root:
            build_root = parsed.build_root
        else:
            build_root = '{}/build_{}'.format(home, parsed.client)

        for config in parsed.configs:
            c.add_config(config)

        c.set_environment('BUILD_ROOT', build_root)
        c.set_environment('CIVET_HOME', home)
        c.set_environment('CIVET_CLIENT_NUMBER', parsed.client)
        if parsed.env:
            for var, value in parsed.env:
                c.set_environment(var, value)

    return c, parsed.daemon

class ClientDaemon(DaemonLite):
    def run(self):
        self.client.run()
    def set_client(self, client):
        self.client = client

def call_daemon(client, cmd):
    home = os.environ.get("CIVET_HOME", os.path.join(os.environ["HOME"], "civet"))
    pfile = os.path.join(home, 'civet_client_%s.pid' % client.client_info["client_name"])
    client_daemon = ClientDaemon(pfile, stdout=client.client_info["log_file"], stderr=client.client_info["log_file"])
    client_daemon.set_client(client)
    if cmd == 'restart':
        client_daemon.restart()
    elif cmd == 'stop':
        client_daemon.stop()
    elif cmd == 'start':
        client_daemon.start()
        print('started')
    elif cmd == 'none':
        client.run()

def main(args):
    client, daemon_cmd = commandline_client(args)
    call_daemon(client, daemon_cmd)

if __name__ == "__main__":
    main(sys.argv[1:])
