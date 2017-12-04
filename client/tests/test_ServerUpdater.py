
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

from django.test import SimpleTestCase
import requests
import time
from client import ServerUpdater
from . import utils
from mock import patch
from threading import Thread

from client import BaseClient
BaseClient.setup_logger()

try:
    from Queue import Queue, Empty
except ImportError:
    from queue import Queue, Empty # Python 3.x

class Tests(SimpleTestCase):
    def setUp(self):
        self.message_q = Queue()
        self.command_q = Queue()
        self.control_q = Queue()
        self.thread = None
        self.updater = None

    @patch.object(requests, 'post')
    @patch.object(requests, 'get')
    def tearDown(self, mock_get, mock_post):
        if self.thread:
            self.control_q.put("Quit")
            self.thread.join()

    def read_q(self, q):
        items = []
        try:
            while True:
                item = q.get(block=False)
                items.append(item)
        except Empty:
            return items

    def create_updater(self):
        client_info = utils.default_client_info()
        updater = ServerUpdater.ServerUpdater(client_info["servers"][0], client_info, self.message_q, self.command_q, self.control_q)
        self.assertEqual(updater.running, True)
        self.assertEqual(sorted(updater.servers.keys()), client_info["servers"])
        self.assertEqual(updater.messages, [])
        return updater

    @patch.object(requests, 'post')
    def test_run(self, mock_post):
        u = self.create_updater()
        u.client_info["server_update_timeout"] = 1
        u.client_info["server_update_interval"] = 1
        self.thread = Thread(target=ServerUpdater.ServerUpdater.run, args=(u,))
        self.thread.start()
        response_data = {"status": "OK"}
        mock_post.return_value = utils.MockResponse(response_data)
        server = u.client_info["servers"][0]
        item = {"server": server, "job_id": 0, "url": "url", "payload": {"message": "message"}}
        self.message_q.put(item)
        time.sleep(2)
        # One call to send the update to the server
        # and one call to ping the other server
        # Depending on the timing though there might be another ping
        self.message_q.join()
        self.control_q.put("Quit")
        self.assertIn(mock_post.call_count, [2,3])

    def test_check_control(self):
        u = self.create_updater()
        self.assertEqual(u.running, True)
        # update the server message
        self.control_q.put({"server": u.main_server, "message": "new message"})
        u.check_control()
        self.assertEqual(u.running, True)
        self.assertEqual(u.servers[u.main_server]["msg"], "new message")
        # update the server message
        self.control_q.put("Anything")
        u.check_control()
        self.assertEqual(u.running, False)

    def test_server_message(self):
        u = self.create_updater()
        server = u.client_info["servers"][0]
        msg = "New Message"
        u.update_server_message(server, msg)
        self.assertEqual(u.servers[server]["msg"], msg)

        u.update_server_message("bad_server", msg)
        self.assertEqual(u.servers.get("bad_server", None), None)

    @patch.object(requests, 'post')
    def test_read_queue(self, mock_post):
        u = self.create_updater()
        server = u.client_info["servers"][0]
        item = {"server": server, "job_id": 0, "url": "url", "payload": {"message": "message"}}
        self.message_q.put(item)
        self.message_q.put(item)
        self.message_q.put(item)
        # should be cleared
        self.assertEqual(len(u.messages), 0)
        u.read_queue()
        self.assertEqual(u.messages, [item, item, item])
        self.assertEqual(u.message_q.qsize(), 0)

    def load_messages(self, u ):
        items = []
        u.messages = []
        for i in range(3):
            item = {"server": u.main_server, "job_id": i, "url": "url", "payload": {"message": "message"}}
            items.append(item)
            u.message_q.put(item)
        u.read_queue()
        return items

    @patch.object(requests, 'post')
    def test_send_messages_ok(self, mock_post):
        u = self.create_updater()
        mock_post.return_value = utils.MockResponse({"status": "OK"})
        items = self.load_messages(u)
        self.assertEqual(u.messages, items)
        self.assertEqual(mock_post.call_count, 0)
        # should be cleared
        u.send_messages()
        self.assertEqual(u.messages, [])
        self.assertEqual(mock_post.call_count, 3)

    @patch.object(requests, 'post')
    def test_send_messages_stop(self, mock_post):
        u = self.create_updater()
        # got the stop signal
        self.load_messages(u)
        response_data = {"status": "OK"}
        mock_post.side_effect = [utils.MockResponse(response_data), utils.MockResponse(response_data, status_code=400)]
        u.send_messages()
        self.assertEqual(u.messages, [])
        self.assertEqual(mock_post.call_count, 2)

    @patch.object(requests, 'post')
    def test_send_messages_cancel(self, mock_post):
        u = self.create_updater()
        # got the cancel signal
        self.load_messages(u)
        response_data = {"status": "OK", "command": "cancel"}
        mock_post.return_value = utils.MockResponse(response_data)
        u.send_messages()
        self.assertEqual(u.messages, [])
        self.assertEqual(mock_post.call_count, 3)

    @patch.object(requests, 'post')
    def test_send_messages_bad_first(self, mock_post):
        u = self.create_updater()
        # server not responding on first response
        response_data = {"status": "OK"}
        items = self.load_messages(u)
        mock_post.call_count = 0
        mock_post.return_value = utils.MockResponse(response_data, do_raise=True)
        u.send_messages()
        self.assertEqual(u.messages, items)
        self.assertEqual(mock_post.call_count, 1)

    @patch.object(requests, 'post')
    def test_send_messages_bad_last(self, mock_post):
        u = self.create_updater()
        # server not responding on last response
        items = self.load_messages(u)
        mock_post.call_count = 0
        response_data = {"status": "OK"}
        mock_post.side_effect = [utils.MockResponse(response_data), utils.MockResponse(response_data), utils.MockResponse(response_data, do_raise=True)]
        u.send_messages()
        self.assertEqual(u.messages, items[2:])
        self.assertEqual(mock_post.call_count, 3)

    @patch.object(requests, 'post')
    def test_send_messages_invalid_json(self, mock_post):
        u = self.create_updater()
        # server not responding correctly
        response_data = {"bad_key": "val"}
        self.load_messages(u)
        mock_post.call_count = 0
        mock_post.return_value = utils.MockResponse(response_data)
        u.send_messages()
        self.assertEqual(u.messages, [])
        self.assertEqual(mock_post.call_count, 3)

    @patch.object(requests, 'post')
    def test_send_messages_invalid(self, mock_post):
        u = self.create_updater()
        # server not responding correctly
        response_data = {"status": "OK"}
        self.load_messages(u)
        mock_post.call_count = 0
        response_data = {"status": "NOT OK"}
        mock_post.return_value = utils.MockResponse(response_data)
        u.send_messages()
        self.assertEqual(u.messages, [])
        self.assertEqual(mock_post.call_count, 3)

    @patch.object(requests, 'post')
    def test_ping_servers(self, mock_post):
        u = self.create_updater()
        mock_post.return_value = utils.MockResponse({"not_empty": True})
        u.client_info["server_update_interval"] = 1
        # not enough elapsed time from creation
        u.ping_servers()
        self.assertEqual(mock_post.call_count, 0)
        time.sleep(1)
        # normal ping
        u.ping_servers()
        self.assertEqual(mock_post.call_count, 2)

        # we shouldn't ping since we just did
        u.ping_servers()
        self.assertEqual(mock_post.call_count, 2)

    @patch.object(requests, 'post')
    def test_ping_server(self, mock_post):
        u = self.create_updater()
        mock_post.return_value = utils.MockResponse({"not_empty": True})
        ret = u.ping_server("server", "message")
        self.assertEqual(ret, True)

        # server didn't respond correctly
        mock_post.return_value = utils.MockResponse({}, do_raise=True)
        ret = u.ping_server("server", "message")
        self.assertEqual(ret, False)

    @patch.object(requests, 'post')
    def test_post_json(self, mock_post):
        u = self.create_updater()
        in_data = {'foo': 'bar'}
        response_data = utils.create_json_response()
        url = 'foo'
        # test the non error operation
        mock_post.return_value = utils.MockResponse(response_data)
        ret = u.post_json(url, in_data)
        self.assertEqual(ret, response_data)

        mock_post.return_value = utils.MockResponse(response_data, do_raise=True)
        #check when the server responds incorrectly
        ret = u.post_json(url, in_data)
        self.assertEqual(ret, None)

        #check when the server gives bad request
        mock_post.return_value = utils.MockResponse(response_data, status_code=400)
        ret = u.post_json(url, in_data)
        self.assertEqual(ret, {"status": "OK", "command": "stop"})

    @patch.object(requests, 'post')
    def test_bad_output(self, mock_post):
        u = self.create_updater()
        mock_post.return_value = utils.MockResponse({"not_empty": True})
        item = {"server": u.main_server, "job_id": 0, "url": "url", "payload": {"output": '\xe0 \xe0'}}
        u.message_q.put(item)
        u.post_message(item)
        self.assertIn("decoded", item["payload"]["output"])

        item["payload"]["foo"] = '\xe0 \xe0'
        with self.assertRaises(ServerUpdater.StopException):
            u.post_message(item)
