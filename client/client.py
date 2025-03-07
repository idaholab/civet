#!/usr/bin/env python

# Copyright 2016-2025 Battelle Energy Alliance, LLC
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
import argparse
import sys, os
import platform
# Need to add parent directory to the path so that imports work
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
from client import BaseClient
from DaemonLite import DaemonLite

class ClientDaemon(DaemonLite):
    def run(self):
        self.client.run()
    def set_client(self, client):
        self.client = client

def call_daemon(client, cmd):
    home = os.environ.get("CIVET_HOME", os.environ["HOME"])
    client.set_environment('CIVET_HOME', home)
    pfile = os.path.join(home, 'civet_client_%s.pid' % client.client_info["client_name"])
    client_daemon = ClientDaemon(pfile, stdout=client.client_info["log_file"], stderr=client.client_info["log_file"])
    client_daemon.set_client(client)
    if cmd == 'restart':
        client_daemon.restart()
    elif cmd == 'stop':
        client_daemon.stop()
    elif cmd == 'start':
        client_daemon.start()

def commandline_client(args):
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", dest='url', help="The URL of the CIVET site.", required=True)
    parser.add_argument("--build-key", type=int, dest='build_key', help="Your build_key", required=True)
    parser.add_argument("--configs",
            dest='configs',
            nargs='+',
            help="The configurations this client supports (eg 'linux-gnu')")
    parser.add_argument("--name", dest='name', help="The name for this particular client. Should be unique.", required=True)
    parser.add_argument("--single-shot",
            dest='single_shot',
            action='store_true',
            help="Execute one test (if there is one) and then exit")
    parser.add_argument("--poll",
            dest='poll',
            type=int,
            default=30,
            help="Number of seconds to wait before polling for more jobs in continuous mode")
    parser.add_argument("--daemon", dest='daemon', choices=['start', 'stop', 'restart'], help="Start a UNIX daemon.")
    parser.add_argument("--log-dir",
            dest='log_dir',
            default='.',
            help="Where to write the log file.  The log will be written as ci_PID.log")
    parser.add_argument("--log-file", dest='log_file', help="Filename to append the log to")
    parser.add_argument("--insecure", dest='insecure', action='store_false', help="Turns off SSL certificate verification")
    parser.add_argument("--ssl-cert",
            dest='ssl_cert',
            help="An crt file to be used when doing SSL certificate verification. This will override --insecure.")
    parser.add_argument("--env",
            dest='env',
            nargs=2,
            action='append',
            help="Sets a client environment variable (example: VAR_NAME VALUE)")
    #parsed, unknown = parser.parse_known_args(args)
    parsed = parser.parse_args(args)

    client_info = {"url": parsed.url,
        "client_name": parsed.name,
        "server": parsed.url,
        "servers": [parsed.url],
        "ssl_verify": parsed.insecure,
        "ssl_cert": parsed.ssl_cert,
        "log_file": parsed.log_file,
        "log_dir": parsed.log_dir,
        "build_keys": [parsed.build_key],
        "single_shot": parsed.single_shot,
        "poll": parsed.poll,
        "daemon_cmd": parsed.daemon,
        "request_timeout": 30,
        "update_step_time": 20,
        "server_update_interval": 20,
        "server_update_timeout": 5,
        "max_output_size": 5*1024*1024
        }

    c = BaseClient.BaseClient(client_info)

    if parsed.daemon == 'start' or parsed.daemon == 'restart' or platform.system() == "Windows":
        if not parsed.configs:
            raise BaseClient.ClientException('--configs must be provided')

        for config in parsed.configs:
            c.add_config(config)

        if parsed.env:
            for var, value in parsed.env:
                c.set_environment(var, value)

        # Add the BUILD_ROOT to the client environment if it exists in the global environment
        # This is to preserve old behavior for folks that are setting the variable before running the client
        if (not parsed.env or 'BUILD_ROOT' not in parsed.env) and 'BUILD_ROOT' in os.environ:
            c.set_environment('BUILD_ROOT', os.environ.get('BUILD_ROOT'))

    return c, parsed.daemon

def main(args):
    client, daemon_cmd = commandline_client(args)
    if daemon_cmd:
        call_daemon(client, daemon_cmd)
    else:
        BaseClient.setup_logger()
        client.run()

if __name__ == "__main__":
    main(sys.argv[1:])
