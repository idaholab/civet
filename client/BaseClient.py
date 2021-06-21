
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
import logging, logging.handlers
from client.JobGetter import JobGetter
from client.JobRunner import JobRunner
from client.ServerUpdater import ServerUpdater
from client.InterruptHandler import InterruptHandler
import os, signal
import time
import traceback

import logging
logger = logging.getLogger("civet_client")

from threading import Thread
try:
    from queue import Queue
except ImportError:
    from Queue import Queue

def has_handler(handler_type):
    """
    Check to see if a handler is already installed.
    Normally this isn't a problem but when running tests it might be.
    """
    for h in logger.handlers:
        # Use type instead of isinstance since the types have
        # to match exactly
        if type(h) == handler_type:
            return True
    return False

def setup_logger(log_file=None):
    """
    Setup the "civet_client" logger.
    Input:
      log_file: If not None then a RotatingFileHandler is installed. Otherwise a logger to console is used.
    """
    formatter = logging.Formatter('%(asctime)-15s:%(levelname)s:%(message)s')
    fhandler = None
    if log_file:
        if has_handler(logging.handlers.RotatingFileHandler):
            return
        fhandler = logging.handlers.RotatingFileHandler(log_file, maxBytes=1024*1024*5, backupCount=5)
    else:
        if has_handler(logging.StreamHandler):
            return
        fhandler = logging.StreamHandler()

    fhandler.setFormatter(formatter)
    logger.addHandler(fhandler)
    logger.setLevel(logging.DEBUG)

class ClientException(Exception):
    pass

class BaseClient(object):
    """
    This is the job server client. It polls the server
    for new jobs, requests one, and then runs it.
    While running a job it reports back with output
    from the job. During this operation the server
    can respond with commands to the the client. Mainly
    to cancel the job.
    """
    def __init__(self, client_info):
        self.client_info = client_info
        self.command_q = Queue()
        self.runner_error = False
        self.thread_join_wait = 2*60*60 # 2 hours

        if self.client_info["log_file"]:
            self.set_log_file(self.client_info["log_file"])
        elif self.client_info["log_dir"]:
            self.set_log_dir(self.client_info["log_dir"])
        else:
            raise ClientException("log file not set")

        setup_logger(self.client_info["log_file"])

        try:
            self.cancel_signal = InterruptHandler(self.command_q, sig=[signal.SIGUSR1, signal.SIGINT])
            self.graceful_signal = InterruptHandler(self.command_q, sig=[signal.SIGUSR2])
        except:
            # On Windows, SIGUSR1, SIGUSR2 are not defined. Signals don't
            # work in general so this is the easiest way to disable
            # them but leave all the code in place.
            self.cancel_signal = InterruptHandler(self.command_q, sig=[])
            self.graceful_signal = InterruptHandler(self.command_q, sig=[])

        if self.client_info["ssl_cert"]:
            self.client_info["ssl_verify"] = self.client_info["ssl_cert"]

    def get_client_info(self, key):
        """
        Returns:
          The client information associated with the given key.
        Raises:
          ClientException: If client info is not found with the given key.
        """
        if key not in self.client_info:
            raise ClientException('Client info with key {} does not exist'.format(key))
        return self.client_info[key]

    def set_client_info(self, key, value):
        """
        Sets the client info with the given key to the given value.
        """
        self.get_client_info(key) # Check for existance
        self.client_info[key] = value

    def set_log_dir(self, log_dir):
        """
        Sets the log dir. If log_dir is set
        the log file name will have a set name of "civet_client_<name>_<pid>.log"
        raises Exception if the directory doesn't exist or isn't writable.
        """
        if not log_dir:
            return

        log_dir = os.path.abspath(log_dir)
        self.check_log_dir(log_dir)
        self.client_info["log_file"] = "%s/civet_client_%s.log" % (log_dir, self.client_info["client_name"])

    def check_log_dir(self, log_dir):
        """
        Makes sure the log directory exists and is writable
        Input:
          log_dir: The directory to check if we can write a log file
        Raises:
          ClientException if unable to write
        """
        if not os.path.isdir(log_dir):
            raise ClientException('Log directory (%s) does not exist!' % log_dir)

        if not os.access(log_dir, os.W_OK):
            raise ClientException('Log directory (%s) is not writeable!' % log_dir)

    def set_log_file(self, log_file):
        """
        Specify a log file to use.
        Input:
          log_file: The log file to write to
        Raises:
          ClientException if we can't write to the file
        """
        if not log_file:
            return

        log_file = os.path.abspath(log_file)

        log_dir = os.path.dirname(log_file)
        self.check_log_dir(log_dir)
        self.client_info["log_file"] = log_file

    def run_claimed_job(self, server, servers, claimed):
        job_info = claimed["job_info"]
        job_id = job_info["job_id"]
        message_q = Queue()
        runner = JobRunner(self.client_info, job_info, message_q, self.command_q)
        self.cancel_signal.set_message({"job_id": job_id, "command": "cancel"})

        control_q = Queue()
        updater = ServerUpdater(server, self.client_info, message_q, self.command_q, control_q)
        for entry in servers:
            if entry != server:
                control_q.put({"server": entry, "message": "Running job on another server"})
            else:
                control_q.put({"server": entry, "message": "Job {}: {}".format(job_id, job_info["recipe_name"])})

        updater_thread = Thread(target=ServerUpdater.run, args=(updater,))
        updater_thread.start();
        runner.run_job()
        if not runner.stopped and not runner.canceled:
            logger.info("Joining message_q")
            message_q.join()
        control_q.put({"command": "Quit"}) # Any command will stop the ServerUpdater

        # We want to wait for a little while here, if necessary.
        # It could be that the server is temporarily down and if
        # we just wait long enough for it to come back we can finish cleanly.
        # However, we don't want to hang forever.
        logger.info("Joining ServerUpdater")
        updater_thread.join(self.thread_join_wait)
        if updater_thread.isAlive():
            logger.warning("Failed to join ServerUpdater thread. Job {}: '{}' not updated correctly".format(
                job_id, job_info["recipe_name"]))
        self.command_q.queue.clear()
        self.runner_error = runner.error

    def run(self):
        """
        Main client loop. Polls the server for jobs and runs them.
        """

        while True:
            do_poll = True
            try:
                getter = JobGetter(self.client_info)
                claimed = getter.find_job()
                if claimed:
                    server = self.get_client_info('server')
                    self.run_claimed_job(server, [server], claimed)
                    # finished the job, look for a new one immediately
                    do_poll = False
            except Exception:
                logger.warning("Error: %s" % traceback.format_exc())

            if self.cancel_signal.triggered or self.graceful_signal.triggered:
                logger.info("Received signal...exiting")
                break

            if self.runner_error:
                logger.info("Error occurred in runner...exiting")
                break

            if self.client_info["single_shot"]:
                break

            if do_poll:
                time.sleep(self.get_client_info('poll'))
