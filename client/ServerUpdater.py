
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
import sys
import time
import json, requests
import traceback
import logging

try:
    from queue import Empty
except ImportError:
    from Queue import Empty

from requests.packages.urllib3.exceptions import InsecureRequestWarning
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

logger = logging.getLogger("civet_client")

class StopException(Exception):
    pass

class ServerUpdater(object):
    def __init__(self, server, client_info, message_q, command_q, control_q):
        self.message_q = message_q
        self.command_q = command_q
        self.control_q = control_q
        self.messages = []
        self.client_info = client_info
        self.servers = {}
        self.main_server = server

        self.update_servers()
        self.running = True
        # We want to make sure we don't send unicode headers
        # Helps prevent the dreaded "Error: [('SSL routines', 'ssl3_write_pending', 'bad write retry')]" errors
        self._headers = {b"User-Agent": b"INL-CIVET-Client/1.0 (+https://github.com/idaholab/civet)"}

    def update_servers(self):
        """
        Initializes the servers
        """
        for server in self.client_info["servers"]:
            self.servers[server] = {"last_time": time.time(), "msg": "Starting up"}

    @staticmethod
    def run(updater):
        """
        Main loop to update the servers.

        This is intended to be called like
        Thread(target=ServerUpdater.run, args=(updater,))
        where updater is a ServerUpdater instance.
        Adding anything to the control queue will cause
        an exit.

        Input:
          updater: A ServerUpdater instance
        """

        while updater.running:
            updater.read_queue()
            updater.send_messages()
            updater.ping_servers()
            updater.check_control()

        # It might be possible that there are more messages, so try one more time
        updater.read_queue()
        updater.send_messages()
        sys.exit(0)

    def update_server_message(self, server, msg):
        """
        Updates the message we send to the server on pings.
        """
        if server not in self.servers:
            logger.info("Unknown server: %s" % server)
        else:
            self.servers[server]["msg"] = msg

    def check_control(self):
        """
        If the parent process wants us to stop then
        they will add something to the control queue
        """
        try:
            msg = self.control_q.get(block=False)
            if isinstance(msg, dict) and "server" in msg:
                if "message" in msg:
                    self.update_server_message(msg["server"], msg["message"])
            else:
                # Anything else on the queue and we stop
                logger.info("ServerUpdater shutting down")
                self.running = False
        except Empty:
            pass

    def read_queue(self):
        """
        Reads the updates from the message queue.

        It stores these in an OrderedDict to be sent to
        the server at a later time.
        We block on the first iteration but don't on further
        iterations so that we can quickly consume the queue.

        Returns: None
        """
        try:
            timeout = self.client_info["server_update_timeout"]
            block = True
            while True:
                item = self.message_q.get(block=block, timeout=timeout)
                self.messages.append(item)
                # if we have an item we don't want to block on the next iteration
                block = False
        except Empty:
            pass

    def send_messages(self):
        """
        Just tries to clear the messages that we haven't sent yet.
        """
        try:
            last_success = 0
            for idx, msg in enumerate(self.messages):
                sent = self.post_message(msg)
                if sent:
                    last_success = idx+1
                    self.message_q.task_done()
                else:
                    break
            #self.messages = self.messages[last_success:]
            self.messages = self.messages[last_success:]
        except StopException:
            for msg in self.messages[last_success:]:
                self.message_q.task_done()
            self.messages = []
        self.servers[self.main_server]["last_time"] = time.time()

    def post_message(self, item):
        """
        Sends a list of updates to the server.

        Input:
          server: the URL of the server
          job_id: The job id associated with the update.
          job_data: A list of updates to send to the server

        Returns:
          True if we could talk to the server, False otherwise
        """
        reply = self.post_json(item["url"], item["payload"])

        if not reply:
            # Since all messages here are on the same server, if there is no
            # reply then there isn't any point in trying with others
            return False

        if "status" not in reply:
            err_str = "While posting to {}, server gave invalid JSON : {}".format(item["url"], reply)
            logger.error(err_str)
        elif reply["status"] != "OK":
            err_str = "While posting to {}, an error occured on the server: {}".format(item["url"], reply)
            logger.error(err_str)
        elif reply.get("command") == "cancel":
            logger.info("ServerUpdater got cancel command for runner")
            self.command_q.put({"server": item["server"], "job_id": item["job_id"], "command": "cancel"})
        elif reply.get("command") == "stop":
            logger.info("ServerUpdater got stop command for runner")
            self.command_q.put({"server": item["server"], "job_id": item["job_id"], "command": "stop"})
            raise StopException

        return True

    def ping_servers(self):
        """
        Updates all servers with a status message.

        If we have recently contacted the server
        then we don't need to contact them again.
        """
        for server, data in self.servers.items():
            current_time = time.time()
            diff = current_time - data["last_time"]
            if diff >= self.client_info["server_update_interval"]:
                self.ping_server(server, data["msg"])
                # the ping could take a bit so use the current time
                # We update the time even if the ping failed so
                # that we aren't constantly hitting the server
                data["last_time"] = time.time()

    def ping_server(self, server, msg):
        url = "{}/client/ping/{}/".format(server, self.client_info["client_name"])
        data = {"message": msg}
        # We let this timeout after a second, if we fail to ping... so what. Hopefully it'll work next time!
        return self.post_json(url, data, timeout=1) != None

    def data_to_json(self, data):
        """
        Convenience function to convert a dict into JSON.
        If the conversion fails then we send back a stop dict.
        Input:
          data[dict]: To be converted to JSON
        Returns:
          tuple(dict/json, bool): The serialized JSON. The bool indicates whether it was successful
        """
        try:
            # Get rid of any possible bad characters
            for k in data.keys():
                # Python 2 and 3 way to see if we are dealing with a byte string.
                # If so, decode it to unicode while getting rid of bad characters
                if isinstance(data[k], b"".__class__):
                    data[k] = data[k].decode("utf-8", "replace")
            in_json = json.dumps(data, separators=(",", ": "))
            # We want to make sure the body is not unicode.
            # Prevents the "Error: [('SSL routines', 'ssl3_write_pending', 'bad write retry')]" errors
            # See https://github.com/urllib3/urllib3/issues/855
            return in_json.encode("utf-8", "replace"), True
        except Exception:
            logger.warning("Failed to convert to json: \n%s\nData:%s" % (traceback.format_exc(), data))
            return {"status": "OK", "command": "stop"}, False

    def post_json(self, request_url, data, timeout=None):
        """
        Post the supplied dict holding JSON data to the url and return a dict
        with the JSON.
        Input:
          request_url: The URL to post to.
          data: dict of data to post.
          timeout: The request timeout; defaults to self.client_info['request_timeout']
        Returns:
          A dict of the JSON reply if successful, otherwise None
        """
        # always include the name so the server can keep track
        data["client_name"] = self.client_info["client_name"]
        logger.info("Posting to '{}'".format(request_url))

        if timeout is None:
            timeout = self.client_info['request_timeout']

        try:
            in_json, good = self.data_to_json(data)
            if not good:
                return in_json
            response = requests.post(request_url,
                    in_json,
                    headers=self._headers,
                    verify=self.client_info["ssl_verify"],
                    timeout=timeout)
            if response.status_code == 400:
                # This means that we shouldn't retry this request
                logger.warning("Stopping because we got a 400 response while posting to: %s" % request_url)
                return {"status": "OK", "command": "stop"}
            if response.status_code == 413:
                # We have too much output, so stop
                logger.warning("Stopping because we got a 413 reponse (too much data) while posting to: %s" % request_url)
                return {"status": "OK", "command": "stop"}
            if response.status_code == 500:
                # There could be a couple of things wrong.
                # 1) We sent some data that the server really doesn't like. This happened
                #    on mammoth testing where the test output spit out null characters which
                #    Postgresql didn't like, causing an internal server error.
                # 2) The server is having issues (can happen when updating the civet source code and DB).
                #    It is likely that is relatively temporary.
                # Since (1) is a bug in the civet server, we shouldn't abort the job. It is good to know
                # though, so log it.
                logger.warning("Got a 500 response (internal server error) while posting to: %s" % request_url)
                return {"status": "OK"}
            response.raise_for_status()
            reply = response.json()
            return reply
        except requests.Timeout:
            logger.warning('POST at {} timed out after {}s'.format(request_url, timeout))
        except Exception:
            logger.warning("Failed to POST at {}.\nError: {}".format(request_url, traceback.format_exc()))
            return None
