
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
import os, re, time
import tempfile
import subprocess, platform
import logging
import contextlib
import signal
import traceback
from distutils import spawn
from typing import Callable
logger = logging.getLogger("civet_client")

try:
    from queue import Queue, Empty
except ImportError:
    from Queue import Queue, Empty

from threading import Thread

@contextlib.contextmanager
def temp_file(*args, **kwargs):
    """
    Context manager for a temporary file that gets deleted when
    not in use.
    The problem with tempfile.NamedTemporaryFile was that it seemed
    to get deleted after closing it. Since this file is meant to be shared
    we want to be able to close it and have others read/close it.
    """
    f = tempfile.NamedTemporaryFile(delete=False, *args, **kwargs)
    try:
        yield f
    finally:
        os.unlink(f.name)

class JobRunner(object):
    def __init__(self, client_info, job, message_q, command_q, build_key):
        """
        Input:
          client_info: A dictionary containing the following keys:
            servers: The URL of the server.
            build_configs: A list of build configs to listen for.
            client_name: The name of the running client
            ssl_verify: Whether to use SSL verification when making a request.
            request_timeout: The timeout when making a request
            build_key: The build_key to be used.
            update_step_time: How often to update the server
          job: A dictionary holding the job information
          message_q: A Queue to add messages to that will be sent to the server.
          command_q: A Queue to read commands from the server.
          build_key: The build key that we are executing with
        """
        self.message_q = message_q
        self.command_q = command_q
        self.build_key = build_key
        self.client_info = client_info
        self.job_data = job
        self.canceled = False
        self.stopped = False
        self.error = False
        self.max_output_size = client_info.get("max_output_size", 5*1024*1024) # Stop collecting after 5Mb

        # To be filled with the environment variables that the client set
        self.civet_client_vars = []
        # To be filled with the environemnt variables that the recipe set (in [Global Environment])
        self.civet_recipe_vars = []

        # The global environment, which is the environment that existed when the client started
        # Note: Windows python hates unicode in environment strings!
        self.global_env = {str(key): str(value) for key, value in os.environ.items()}

        # The local environment, which is the environment set explicitly by the client
        # (with --env) and the environment set explicitly by the recipe
        self.local_env = {}
        # Add variables explicitly set by the client
        if 'environment' in self.client_info:
            self.local_env.update(self.client_info['environment'])
            self.civet_client_vars = list(self.client_info['environment'].keys())
        # For backwards compatability
        # Add the environment from the recipe (in [Global Environment])
        env_dict = self.env_to_dict(self.job_data.get("environment", {}))
        self.civet_recipe_vars = list(env_dict.keys())
        self.local_env.update(env_dict)
        self.clean_env(self.local_env)

        # concatenate all the pre-step sources into one.
        self.all_sources = ""
        for pre_step_source in self.job_data['prestep_sources']:
            self.all_sources += '{}\n'.format(pre_step_source.replace('\r', ''))

        for step in self.job_data["steps"]:
            # for backwards compatability
            env_dict = self.env_to_dict(step.get("environment", {}))
            self.clean_env(env_dict)
            env_dict["client_name"] = client_info["client_name"]
            step["environment"] = env_dict
            step["script"] = step["script"].replace("\r", "")

        self.max_step_time = int(self.local_env.get("CIVET_MAX_STEP_TIME", 6*60*60)) # Kill job after this number of seconds

        # Entry point for running something before each runner step;
        # would be a function that takes an env (the step env) and returns
        # False it it failed
        self.pre_step = None
        # Entry point for running something after each runner step;
        # would be a function that takes an env (the step env) and returns
        # False it it failed
        self.post_step = None

    def env_to_dict(self, env):
        """
        For some reason the environment used to be passed in as tuples.
        The new way to pass them in is in a dict. This
        is here until everything is using the new way.
        Input:
          env: a list of tuples or a dict representing the environment
        """
        if isinstance(env, list):
            d = {}
            for t in env:
                d[str(t[0])] = str(t[1])
            return d
        elif isinstance(env, dict):
            return {str(k): str(v) for k, v in env.items()}
        return {}

    def run_job(self, fail: bool = False):
        """
        Runs the job as specified in the constructor.
        Returns:
          A dict with the following keys:
            canceled: bool: Whether the job was canceled
            failed: bool: Whether the job failed
            seconds: int: Total runtime in seconds for the job
            complete: bool: Whether it is complete
            client_name: str: Name of this client
        """
        job_start_time = time.time()

        job_msg = {'canceled': False, 'failed': False}
        steps = self.job_data['steps']

        logger.info('Starting job %s on %s on server %s' % (self.job_data['recipe_name'],
            self.local_env['CIVET_BASE_REPO'],
            self.client_info["server"]))

        job_id = self.job_data["job_id"]
        for step in steps:
            if fail:
                self.error = True
            else:
                results = self.run_step(step)

            if self.error:
                job_msg["canceled"] = True
                job_msg["failed"] = True
                break

            if self.stopped:
                logger.info("Received stop command")
                break

            if self.canceled:
                logger.info("Received cancel command")
                job_msg["canceled"] = True
                break

            if results.get('exit_status', 1) == 86:
                logger.info('Step skipped')
                break

            if results.get("exit_status", 1) != 85 and results.get("exit_status", 1) != 0 and step.get("abort_on_failure", True):
                job_msg["failed"] = True
                logger.info('Step failed. Stopping')
                break

        job_msg['seconds'] = int(time.time() - job_start_time) # would be float
        job_msg['complete'] = True
        job_msg['client_name'] = self.client_info["client_name"]

        final_url = "{}/client/job_finished/{}/{}/{}/".format(self.client_info["server"],
                self.build_key,
                self.client_info["client_name"],
                job_id)
        self.add_message(final_url, job_msg)

        logger.info("Finished Job {}: {}".format(job_id, self.job_data['recipe_name']))
        return job_msg

    def add_message(self, url, msg):
        """
        Puts a message on the message queue that will be read in by the ServerUpdater.
        Input:
          url: str: URL the ServerUpdater will post to.
          msg: dict: Payload to post to the URL
        """
        self.message_q.put({"server": self.client_info["server"],
            "job_id": self.job_data["job_id"],
            "url": url,
            "payload": msg.copy()})

    def update_step(self, stage, step, chunk_data):
        """
        Just figures out what URL to use and adds the message
        to the message queue.
        Input:
          stage: str: One of "start", "complete", or "update" to indicate what stage this message should be sent to.
          step: dict: Holds information about the current step
          chunk_data: This will be the payload that is posted to the server
        """
        options = {"start": "start_step_result", "complete": "complete_step_result", "update": "update_step_result"}
        keyword = options.get(stage, "update_step_result")

        url = "{}/client/{}/{}/{}/{}/".format(self.client_info["server"],
                keyword,
                self.build_key,
                self.client_info["client_name"],
                step["stepresult_id"])
        self.add_message(url, chunk_data)

    def get_output_from_queue(self, q, timeout=1):
        """
        Grabs all the available output from the queue and returns it.
        This is used with reading the output of a subprocess so everything on
        the queue should just be strings.

        On the first run through we block if timeout is non zero. This will slow down the overall
        read process loop so that we are not constantly busy waiting trying
        to read the output.
        Input:
          q: Queue to read from
          timeout: int: How long to block while trying to read
        Return:
          list: str: Output read.
        """
        output = []
        block = False
        if timeout:
            block = True

        try:
            while True:
                line = q.get(block=block, timeout=timeout)
                output.append(line)
                block = False
        except Empty:
            """
            We always return from here since eventually we will
            read all the messages on the queue and trigger an Empty exception.
            """
            return output

    def read_command(self):
        """
        Reads a command from the command queue.

        This will read ALL of the commands from the queue.
        If the command is for another job it will be dropped.
        """
        try:
            while True:
                cmd = self.command_q.get(block=False)
                if cmd.get("command") == "cancel":
                    logger.info("Read cancel command")
                    self.canceled = True
                elif cmd.get("command") == "stop":
                    logger.info("Read stop command")
                    self.stopped = True
                else:
                    logger.warning("Received unknown command '%s'" % cmd)
        except Empty:
            pass

    def read_process_output(self, proc, step, step_data):
        """
        This reads the output of a process and adds messages
        to the message queue.
        Input:
          proc: subprocess.Popen instance
          step: dict: Holds general step information
          step_data: dict: Holds result for the step
        Return:
          dict: An updated step_data
        """
        out = []
        chunk_out = []
        start_time = time.time()
        max_end_time = start_time + int(step["environment"].get("CIVET_MAX_STEP_TIME", self.max_step_time))
        chunk_start_time = time.time()
        step_data["canceled"] = False
        over_max = False
        keep_output = False

        # This allows non-blocking read on Unix & Windows
        # See: http://stackoverflow.com/questions/375427/non-blocking-read-on-a-subprocess-pipe-in-python
        def enqueue_output(out, queue):
            for line in iter(out.readline, b''):
                if line:
                    # Make sure it doesn't have any bad unicode characters
                    line = line.decode("utf-8", "replace")
                queue.put(line)
            out.close()

        q = Queue()
        t = Thread(target=enqueue_output, args=(proc.stdout, q))
        t.daemon = True
        t.start();

        while proc.poll() is None:
            if self.canceled or self.stopped:
                logger.info("Killing job\n")
                self.kill_job(proc)
                step_data['canceled'] = True
                step_data['output'] = ""
                break

            output = self.get_output_from_queue(q)
            if output and not over_max:
                out.extend(output)
                chunk_out.extend(output)

            # Don't worry that "out" might contain multibyte characters, we
            # just want a rough size check
            if not over_max and len("".join(out)) >= self.max_output_size:
                over_max = True
                out.append("\n\n*****************************************************\n\n")
                out.append("CIVET: Output size exceeded limit (%s bytes), further output will not be displayed!\n"
                        % self.max_output_size)
                out.append("\n*****************************************************\n")

            diff = time.time() - chunk_start_time
            if diff > self.client_info["update_step_time"]: # Report some output every x seconds
                step_data['output'] = "".join(chunk_out)
                step_data['time'] = int(time.time() - start_time)
                self.update_step("update", step, step_data)
                chunk_out = []

                chunk_start_time = time.time()

            if time.time() > max_end_time:
                self.canceled = True
                keep_output = True
                out.append("\n\n*****************************************************\n")
                out.append("CIVET: Cancelling job due to step taking longer than the max %s seconds\n" % self.max_step_time)
                out.append("\n*****************************************************\n")

            self.read_command() # this will set the internal flags to cancel or stop

        t.join() # make sure the step has no more output

        # we might not have gotten everything
        out.extend(self.get_output_from_queue(q, timeout=0))
        if not step_data['canceled'] or keep_output:
            step_data['output'] = ''.join(out)
        step_data['complete'] = True
        step_data['time'] = int(time.time() - start_time) #would be float
        return step_data

    def kill_job(self, proc):
        """
        If the job gets cancelled then we need to
        kill the running job.
        On Unix we created a process group so that we can kill
        the subprocess and all of its children. If that doesn't work
        then we do a hard kill -9 on it.
        Input:
          proc: subprocess.Popen instance
        """
        try:
            for i in range(5): # just try a few times to absolutely kill it
                if self.is_windows():
                    # Apparently using taskkill is a better way to kill a job
                    # with all of its children. Don't have a windows box to test it on.
                    if spawn.find_executable("taskkill"):
                        subprocess.call(['taskkill', '/F', '/T', '/PID', str(proc.pid)])
                    else:
                        proc.terminate()
                else:
                    pgid = os.getpgid(proc.pid)
                    logger.info("Sending SIGTERM to process group %s of pid %s" % (pgid, proc.pid))
                    os.killpg(pgid, signal.SIGTERM)
                time.sleep(1)
                if proc.poll() is not None:
                    break

            if proc.poll() is None:
                logger.warning("Trying to forcefully kill %s" % proc.pid)
                proc.kill()

            # We can sometimes get a warning if this isn't closed
            # Note that we set stderr to stdout when we create the process
            if proc.stdout:
                proc.stdout.close()

            if proc.poll() is None:
                logger.warning("Unable to kill process %s." % proc.pid)
            else:
                logger.warning("%s killed as requested." % proc.pid)
        except Exception as e:
            # this will be due to trying to kill a process that is already dead
            logger.warning("Exception occured while killing job: %s" % e)

    def is_windows(self):
        """
        Simple check to see if we are on windows
        Return:
          bool: True if we are on windows else False
        """
        return platform.system() == "Windows"

    def create_process(self, script_name, env, devnull):
        """
        Creates a subprocess to run the script
        Input:
          script_name: str: Name of the temporary file of the script to run
          env: dict: Holds the environment
          devnull: file object that will be used as stdin
        Return:
          subprocess.Popen that was created
        """
        # On windows, we will take the global environment and then update it
        # with the step environment (client, recipe, and step) and use it
        # in the subprocess
        if self.is_windows():
            combined_env = self.global_env.copy()
            combined_env.update(env)
            exec_cmd = os.path.join(os.path.dirname(__file__), "scripts", "mingw64_runcmd.bat")
            return subprocess.Popen(
                [exec_cmd, script_name],
                env=combined_env,
                shell=False,
                stdin=devnull,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
                )
        # On linux, we will only run with the global environment and we inject
        # the step environment (client, recipe, and step). This is why we
        # run the subprocess with only the global environment
        else:
            return subprocess.Popen(
                ['/bin/bash', script_name],
                env=self.global_env,
                shell=False,
                cwd="/",
                stdin=devnull,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                preexec_fn=os.setsid,
                )

    def run_platform_process(self, step, step_env, step_data):
        """
        Run the script for the step.
        We write out a single file that includes all the environment
        sources followed by the actual script.
        We want to create the process using a process group so that
        if we need to kill it then all the children will get killed
        as well.
        Input:
          step: dict: Holds the step information
          step_env: dict: Holds the environment the step will be run with
          step_data: dict: Holds the results of the step
        Return:
          dict: An updated version of step_data
        """
        proc = None

        def trigger_error(step_data, reason):
            # The main error that we are trying to catch is IOError (out of disk space)
            # but there might be others
            if proc and proc.poll() is None:
                self.kill_job(proc)
            logger.error(reason)
            self.error = True
            step_data["output"] = err_str
            step_data['exit_status'] = 1
            self.update_step("complete", step, step_data)
            return step_data

        def trigger_exception(step_data):
            delimiter = '-'*60
            err_str = "\n%s\n\n" % delimiter
            err_str += "Unknown error occurred in the civet client! Canceling job and quitting."
            err_str += "\nJob  : %s: %s" % (self.job_data["job_id"], self.job_data["recipe_name"])
            err_str += "\nStep : %s" % step["step_name"]
            err_str += "\nError:\n%s" % traceback.format_exc()
            err_str += "\n%s" % delimiter
            return trigger_error(step_data, err_str)

        # Execute the pre step hook, if any
        if self.pre_step:
            try:
                if not self.pre_step(step_env):
                    return trigger_error(step_data, 'JobRunner pre_step failed')
            except:
                return trigger_exception(step_data)

        try:
            with temp_file() as step_script:
                # If we're not in windows, we will inject the client and step' additional
                # environment into the script itself. This makes the script portable
                # (for example, running it in another server from within the client)
                if not self.is_windows():
                    step_script.write('#!/bin/bash\n\n'.encode('utf-8'))
                    step_script.write('# BEGIN CIVET STEP ENVIRONMENT\n'.encode('utf-8'))
                    for var, value in step_env.items():
                        step_script.write('export {}="{}"\n'.format(var, value).encode('utf-8'))
                    step_script.write('# END CIVET STEP ENVIRONMENT\n\n'.encode('utf-8'))

                step_script.write(self.all_sources.encode('utf-8'))
                step_script.write('\n{}\n'.format(step['script']).encode('utf-8'))
                step_script.flush()
                step_script.close()
                with open(os.devnull, "wb") as devnull:
                    proc = None
                    try:
                        proc = self.create_process(step_script.name, step_env, devnull)
                    except Exception as e:
                        proc = None
                        err_str = "Couldn't create process: %s" % e
                        logger.error(err_str)
                        self.stopped = True
                        step_data["output"] = err_str
                        step_data['exit_status'] = 1
                        self.update_step("complete", step, step_data)
                        return step_data
                    step_data = self.run_step_process(proc, step, step_data)
        except Exception:
            step_data = trigger_exception(step_data)

        # Execute the post step hook, if any
        if self.post_step:
            try:
                if not self.post_step(step_env):
                    return trigger_error(step_data, 'JobRunner post_step failed')
            except:
                return trigger_exception(step_data)

        # Suceeded
        return step_data

    def run_step_process(self, proc, step, step_data):
        """
        Reads the output of the passed in process.
        If an exception occurs assume that the process has been
        canceled, either by signal or by command from the server.
        Input:
          proc: subprocess.Popen instance
          step: dict: Holds step information
          step_data: dict: Holds step result information
        Return:
          dict: An updated version of step_data
        """
        step_start = time.time()
        try:
            step_data = self.read_process_output(proc, step, step_data)
            if not self.canceled and not self.stopped:
                proc.wait() # To get the returncode set
        except Exception:
            # This shouldn't really happend but if it does just kill it.
            logger.info("Caught exception while running job {}\nError:{}\n".format(step_data['job_id'], traceback.format_exc()))
            self.kill_job(proc)
            step_data['canceled'] = True
            self.canceled = True
            step_data['output'] = ''

        step_data['exit_status'] = proc.returncode
        step_data['time'] = int(time.time() - step_start) #would be float

        self.update_step("complete", step, step_data)

        return step_data

    def run_step(self, step):
        """
        Runs one of the steps of the job.
        Input:
          step: dict: Holds step information
        Return:
          dict: Holds step_result information
        """

        step_data = {
          'job_id': self.job_data["job_id"],
          'client_name': self.client_info["client_name"],
          'stepresult_id': step['stepresult_id'],
          'step_num': step['step_num'],
          'output': None,
          'exit_status': 0,
          'complete': False,
          'time': 0,
          'canceled': False,
          }

        logger.info('Starting step %s' % step['step_name'])

        self.update_step("start", step, step_data)

        # copy the env so we don't pollute the global env
        step_env = self.local_env.copy()
        step_env.update(step["environment"])

        # Store a list of variables that the step set
        civet_step_vars = list(step['environment'].keys())
        step_env['CIVET_STEP_VARS'] = ' '.join(sorted(civet_step_vars))

        # Store a list of variables that the recipe set. If the step overrides
        # one of the variables set in the recipe, don't show it as set by the recipe
        civet_recipe_vars = []
        for var in self.civet_recipe_vars:
            if var not in civet_step_vars:
                civet_recipe_vars.append(var)
        step_env['CIVET_RECIPE_VARS'] = ' '.join(sorted(civet_recipe_vars))

        # Store a list of variables that the client set. If the step or the recipe
        # overrides one of the variable set by the client, don't show it as set by the client
        civet_client_vars = []
        for var in self.civet_client_vars:
            if var not in civet_step_vars and var not in civet_recipe_vars:
                civet_client_vars.append(var)
        step_env['CIVET_CLIENT_VARS'] = ' '.join(sorted(civet_client_vars))


        return self.run_platform_process(step, step_env, step_data)

    def clean_env(self, env):
        """
        Clean a dict to be used in as the environment for a step.
        Input:
          dict: environment variables
        """
        for key, value in env.items():
            env[str(key)] = str(self.replace_environment(str(value)))

    def replace_environment(self, env_value):
        """
        Just replace occurences of "^BUILD_ROOT" with the actual build root
        Input:
          str: environment value to check
        Return:
          str: environment value with replacements done (if any)
        """
        build_root = self.client_info['environment'].get('BUILD_ROOT', os.getcwd())
        return re.sub("^BUILD_ROOT", build_root, str(env_value))
