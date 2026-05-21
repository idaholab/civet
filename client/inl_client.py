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
import os, sys, argparse, pwd
# Need to add parent directory to the path so that imports work
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
import socket
import platform
import logging, logging.handlers
from client import INLClient, BaseClient

def commandline_client(args):
    parser = argparse.ArgumentParser()
    parser.add_argument('--client', dest='client', type=int, help='The number of the client.', required=True)
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
    parser.add_argument('--startup-command',
                        type=str,
                        dest='startup_command',
                        help='A command to run on startup')
    parser.add_argument('--pre-job-command',
                        type=str,
                        dest='pre_job_command',
                        help='A command to run before a job')
    parser.add_argument('--pre-step-command',
                        type=str,
                        dest='pre_step_command',
                        help='A command to run before a step')
    parser.add_argument('--post-job-command',
                        type=str,
                        dest='post_job_command',
                        help='A command to run after a job')
    parser.add_argument('--post-step-command',
                        type=str,
                        dest='post_step_command',
                        help='A command to run after a step')
    parser.add_argument('--exit-command',
                        type=str,
                        dest='exit_command',
                        help='A command to run on client exit')

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
        "build_keys": [],
        "single_shot": False,
        "request_timeout": 120,
        "update_step_time": 30,
        "server_update_timeout": 5,
        # This needs to be bigger than update_step_time so that
        # the ping message doesn't become the default message
        "server_update_interval": 50,
        "max_output_size": 5*1024*1024,
        "startup_command": parsed.startup_command,
        "pre_job_command": parsed.pre_job_command,
        "pre_step_command": parsed.pre_step_command,
        "post_job_command": parsed.post_job_command,
        "post_step_command": parsed.post_step_command,
        "exit_command": parsed.exit_command
    }

    c = INLClient.INLClient(client_info)

    # Add a syslog logger
    if platform.system() != 'Windows':
        log_device = '/dev/log' if platform.system() == 'Linux' else '/var/run/syslog'
        syslog_tag = client_name.replace(socket.gethostname() + '_', '')
        syslog_handler = logging.handlers.SysLogHandler(log_device)
        syslog_formatter = logging.Formatter(syslog_tag + ': %(message)s')
        syslog_handler.setFormatter(syslog_formatter)
        syslog_handler.setLevel(logging.INFO)
        logger = logging.getLogger("civet_client")
        logger.addHandler(syslog_handler)

    if not parsed.configs:
        raise INLClient.ClientException('--configs must be provided')

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

    return c

if __name__ == "__main__":
    commandline_client(sys.argv[1:]).run()
