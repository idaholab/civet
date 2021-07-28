
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
from client import BaseClient, Modules, settings
import os
import time, traceback
from client.JobGetter import JobGetter
import logging
logger = logging.getLogger("civet_client")

class INLClient(BaseClient.BaseClient):
    """
    The INL version of the build client.
    Loads the appropiate environment based on the build config
    """
    def __init__(self, client_info):
        super(INLClient, self).__init__(client_info)
        self.modules = Modules.Modules()
        self.check_settings()
        self.client_info["servers"] = [ s[0] for s in settings.SERVERS ]

    def check_server(self, server):
        """
        Checks a single server for a job, and if found, runs it.
        Input:
          server: tuple: (The URL of the server to check, build_key, bool: whether to check SSL)
        Returns:
          bool: True if we ran a job, False otherwise
        """
        self.client_info["server"] = server[0]
        self.client_info["build_key"] = server[1]
        self.client_info["ssl_verify"] = server[2]
        getter = JobGetter(self.client_info)
        claimed = getter.find_job()
        if claimed:
            load_modules = settings.CONFIG_MODULES[claimed['config']]
            os.environ["CIVET_LOADED_MODULES"] = ' '.join(load_modules)
            self.modules.clear_and_load(load_modules)
            self.run_claimed_job(server[0], [ s[0] for s in settings.SERVERS ], claimed)
            return True
        return False

    def check_settings(self):
        """
        Do some basic checks to make sure the settings are good.
        Raises:
          Exception: If there was a problem with settings
        """
        modules_msg = "settings.CONFIG_MODULES needs to be a dict of build configs!"
        try:
            if not isinstance(settings.CONFIG_MODULES, dict):
                raise Exception(modules_msg)
        except:
            raise Exception(modules_msg)

        servers_msg = "settings.SERVERS needs to be a list of servers to poll!"
        try:
            if not isinstance(settings.SERVERS, list):
                raise Exception(servers_msg)
        except:
            raise Exception(servers_msg)

        env_msg = "settings.ENVIRONMENT needs to be a dict of name value pairs!"
        try:
            if not isinstance(settings.ENVIRONMENT, dict):
                raise Exception(env_msg)
        except:
            raise Exception(env_msg)


    def run(self, single=False):
        """
        Main client loop. Polls the server for jobs and runs them.
        Loads the proper environment for each config.
        Inputs:
          single: If True then it will only check the servers once. Othwerise it will poll.
        Returns:
          None
        """
        for k, v in settings.ENVIRONMENT.items():
            os.environ[str(k)] = str(v)

        logger.info('Starting {} with MOOSE_JOBS={}'.format(self.client_info["client_name"], os.environ['MOOSE_JOBS']))
        logger.info('Build root: {}'.format(os.environ['BUILD_ROOT']))
        self.client_info["build_configs"] = list(settings.CONFIG_MODULES.keys())

        # Do a clear_and_load here in case there is a problem with the module system.
        # We don't want to run if we can't do modules.
        self.modules.clear_and_load([])

        while True:
            ran_job = False
            for server in settings.SERVERS:
                if self.cancel_signal.triggered or self.graceful_signal.triggered or self.runner_error:
                    break
                try:
                    if self.check_server(server):
                        ran_job = True
                except Exception:
                    logger.debug("Error: %s" % traceback.format_exc())
                    break

            if self.cancel_signal.triggered or self.graceful_signal.triggered:
                logger.info("Received signal...exiting")
                break
            if self.runner_error:
                logger.info("Error in runner...exiting")
                break
            if single:
                break
            if not ran_job:
                time.sleep(self.client_info["poll"])
