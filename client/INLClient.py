
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
import shutil
from inspect import signature
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
        self.client_info["manage_build_root"] = settings.MANAGE_BUILD_ROOT
        self.client_info["jobs_ran"] = 0
        self.client_info["config_modules"] = {}

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
            if self.get_client_info('manage_build_root'):
                self.create_build_root()

            if claimed['config'] in self.get_client_info('config_modules'):
                modules = self.get_client_info('config_modules')[claimed['config']]
                self.set_environment('CIVET_LOADED_MODULES', ' '.join(modules))
                self.modules.clear_and_load(modules)
            else:
                self.set_environment('CIVET_LOADED_MODULES', '')
                self.modules.clear_and_load(None)

            self.run_claimed_job(server[0], [ s[0] for s in settings.SERVERS ], claimed)
            self.set_client_info('jobs_ran', self.get_client_info('jobs_ran') + 1)

            if self.get_client_info('manage_build_root'):
                self.remove_build_root()

            return True
        return False

    def check_settings(self):
        """
        Do some basic checks to make sure the settings are good.
        Raises:
          Exception: If there was a problem with settings
        """
        servers_msg = "settings.SERVERS needs to be a list of servers to poll!"
        try:
            if not isinstance(settings.SERVERS, list):
                raise Exception(servers_msg)
        except:
            raise Exception(servers_msg)

        if hasattr(settings, "MANAGE_BUILD_ROOT"):
            if not isinstance(settings.MANAGE_BUILD_ROOT, bool):
                raise Exception("settings.MANAGE_BUILD_ROOT needs to a boolean!")
        else:
            logger.info("MANAGE_BUILD_ROOT setting not set; defaulting to false")
            settings.MANAGE_BUILD_ROOT = False

    def check_build_root(self):
        """
        Checks if the build root can be created and removed.
        """
        logger.info("Checking BUILD_ROOT {} for creation and removal".format(self.get_build_root()))

        if self.build_root_exists():
            logger.warning("BUILD_ROOT {} already exists; removing".format(self.get_build_root()))
            self.remove_build_root()

        self.create_build_root()
        self.remove_build_root()

    def add_config_module(self, config, module):
        if config not in self.get_client_info("build_configs"):
            raise BaseClient.ClientException('config {} is not a valid build config'.format(config))
        if not isinstance(module, str):
            raise BaseClient.ClientException('module must be a str')
        if config not in self.get_client_info("config_modules"):
            self.client_info["config_modules"][config] = []
        self.client_info["config_modules"][config].append(module)

    def get_build_root(self):
        """
        Gets the build root.
        Raises:
          BaseClient.ClientException: If the BUILD_ROOT env variable is not set.
        """
        return self.get_environment('BUILD_ROOT')

    def build_root_exists(self):
        """
        Returns:
          True if the BUILD_ROOT exists, False otherwise
        """
        return os.path.isdir(self.get_build_root())

    def remove_build_root(self):
        """
        Removes the build root.
        Raises:
          BaseClient.ClientException: If BUILD_ROOT does not exist, or the directory removal failed.
        """
        build_root = self.get_build_root()

        if self.build_root_exists():
            logger.info('Removing BUILD_ROOT {}'.format(build_root))
            shutil.rmtree(build_root)
        else:
            raise BaseClient.ClientException('Failed to remove BUILD_ROOT {}; it does not exist'.format(build_root))

    def create_build_root(self):
        """
        Creates the build root.
        Raises:
          BaseClient.ClientException: If the BUILD_ROOT directory could not be created or if it already exists.
        """
        build_root = self.get_build_root()
        if self.build_root_exists():
            raise BaseClient.ClientException('Failed to create BUILD_ROOT {}; it already exists'.format(build_root))
        else:
            try:
                os.mkdir(build_root)
                logger.info('Created BUILD_ROOT {}'.format(build_root))
            except:
                logger.exception('Failed to create BUILD_ROOT {}'.format(build_root))
                raise

    def run(self, exit_if=None):
        """
        Main client loop. Polls the server for jobs and runs them.
        Loads the proper environment for each config.
        Inputs:
          exit_if: Optional function with a single parameter (which is passed as self; this client)
                   that returns a bool. If the function returns True, exit the poll loop at that
                   time (checked at the end of the poll loop). Used in testing.
        Returns:
          None
        """
        logger.info('Starting client {}'.format(self.get_client_info('client_name')))
        logger.info('Build root: {}'.format(self.get_build_root()))

        if exit_if is not None and (not callable(exit_if) or len(signature(exit_if).parameters) != 1):
            raise BaseClient.ClientException('exit_if must be callable with a single parameter (the client)')

        # Deprecated environment setting; you should start the client with the vars set instead
        if hasattr(settings, 'ENVIRONMENT') and settings.ENVIRONMENT is not None:
            logger.info('DEPRECATED: Set environment variables manually instead of using settings.ENVIRONMENT')
            for k, v in settings.ENVIRONMENT.items():
                self.set_environment(k, v)

        # Depcreated build config setting; you should add with add_config_module() or --config-module instead
        if hasattr(settings, 'CONFIG_MODULES') and settings.CONFIG_MODULES is not None:
            logger.info('DEPRECATED: Set config modules with --configs and --config-module/add_config_module() instead of settings.CONFIG_MODULES')
            for config, modules in settings.CONFIG_MODULES.items():
                if config not in self.get_client_info('build_configs'):
                    self.add_config(config)
                for module in modules:
                    if config not in self.get_client_info('config_modules') or module not in self.get_client_info('config_modules')[config]:
                        self.add_config_module(config, module)

        logger.info('Available configs: {}'.format(' '.join([config for config in self.get_client_info("build_configs")])))

        # Do a clear_and_load here in case there is a problem with the module system.
        # We don't want to run if we can't do modules.
        self.modules.clear_and_load([])

        while True:
            if self.get_client_info('manage_build_root') and self.build_root_exists():
                logger.warning("BUILD_ROOT {} already exists at beginning of poll loop; removing"
                               .format(self.get_build_root()))
                self.remove_build_root()

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
            if exit_if is not None:
                should_exit = exit_if(self)
                if type(should_exit) != bool:
                    raise BaseClient.ClientException('exit_if must return type bool')
                if should_exit:
                    break
            if not ran_job:
                time.sleep(self.get_client_info('poll'))

        if self.get_client_info('manage_build_root') and self.build_root_exists():
            logger.warning("BUILD_ROOT {} still exists after exiting poll loop; removing"
                           .format(self.get_build_root()))
            self.remove_build_root()
