
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

import time
from client import ServerUpdater
from ci import models
import LiveClientTester
from Queue import Queue

class Tests(LiveClientTester.LiveClientTester):
    def setUp(self):
        super(Tests, self).setUp()
        self.message_q = Queue()
        self.command_q = Queue()
        self.control_q = Queue()
        self.thread = None
        self.updater = None
        self.updater = ServerUpdater.ServerUpdater(self.client_info["servers"][0], self.client_info, self.message_q, self.command_q, self.control_q)
        self.assertEqual(self.updater.running, True)
        self.assertEqual(self.updater.servers.keys(), self.client_info["servers"])
        self.assertEqual(self.updater.messages, [])

    def tearDown(self):
        super(Tests, self).tearDown()
        if self.thread:
            self.control_q.put("Quit")
            self.thread.join()

    def set_before(self, client=None):
        self.num_clients = models.Client.objects.count()
        if client:
            self.last_seen = client.last_seen
            self.status = client.status
        else:
            self.last_seen = None
            self.status = None

    def compare_after(self, client=None, clients=0, greater=False, same=False, status=None):
        self.assertEqual(self.num_clients + clients, models.Client.objects.count())
        if client:
            client.refresh_from_db()
            self.assertEqual(client.status, status)
            if greater:
                self.assertGreater(client.last_seen, self.last_seen)
            elif same:
                self.assertEqual(client.last_seen, self.last_seen)

    def test_ping(self):
        self.client_info["server_update_interval"] = 1
        self.set_before()
        self.set_counts()
        # not enough elapsed time since creation
        self.updater.ping_servers()
        self.compare_counts()
        self.compare_after()

        time.sleep(1)
        # OK
        self.set_before()
        self.set_counts()
        self.updater.ping_servers()
        self.compare_counts(num_clients=1)
        self.compare_after(clients=1)
        client = models.Client.objects.latest()

        client.status = models.Client.IDLE
        client.save()
        # we shouldn't ping since we just did
        self.set_counts()
        self.set_before(client)
        self.updater.ping_servers()
        self.compare_counts()
        self.compare_after(client=client, status=models.Client.IDLE, same=True)

        # we should ping and the client should be updated
        self.set_before(client)
        time.sleep(self.client_info["server_update_interval"]+1)
        self.set_counts()
        self.updater.ping_servers()
        self.compare_counts()
        self.compare_after(client=client, status=models.Client.RUNNING, greater=True)
