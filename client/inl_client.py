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
import os, sys, argparse
# Need to add parent directory to the path so that imports work
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
import socket
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
    parser.add_argument('--config-modules',
                        dest='config_modules',
                        type=str,
                        nargs='+',
                        action='append',
                        help='Add module(s) to load to the given config (eg linux-gnu some-module another-module)')
    parser.add_argument("--env",
            dest='env',
            nargs=2,
            action='append',
            help="Sets a client environment variable (example: VAR_NAME VALUE)")
    parser.add_argument("--build-root",
            type=str,
            dest='build_root',
            help="Sets the build root")

    parsed = parser.parse_args(args)
    home = os.environ.get("CIVET_HOME", os.path.join(os.environ["HOME"], "civet"))

    log_dir = '{}/logs'.format(home)
    client_name = '{}_{}'.format(socket.gethostname(), parsed.client)
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
        "poll": 30,
        "daemon_cmd": parsed.daemon,
        "request_timeout": 120,
        "update_step_time": 20,
        "server_update_timeout": 5,
        # This needs to be bigger than update_step_time so that
        # the ping message doesn't become the default message
        "server_update_interval": 40,
        "max_output_size": 5*1024*1024
        }

    c = INLClient.INLClient(client_info)

    if parsed.daemon == 'start' or parsed.daemon == 'restart':
        if not parsed.configs:
            raise BaseClient.ClientException('--configs must be provided when starting or restarting')

        if parsed.build_root:
            build_root = parsed.build_root
        else:
            build_root = '{}/build_{}'.format(home, parsed.client)

        for config in parsed.configs:
            c.add_config(config)

        if parsed.config_modules:
            for entry in parsed.config_modules:
                config = entry[0]
                if len(entry) < 2:
                    raise BaseClient.ClientException('--config-module entry {} must contain modules'.format(config))
                modules = entry[1:]
                for module in modules:
                    c.add_config_module(config, module)

        c.set_environment('BUILD_ROOT', build_root)
        c.set_environment('CIVET_HOME', home)
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
