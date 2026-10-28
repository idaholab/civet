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

import json
import threading
import time
import unittest
from django.core.cache import cache
from django.db import connection, connections
from django.test import Client, TransactionTestCase
from django.urls import reverse
from mock import patch
from ci.client import views
from ci.tests import utils


@unittest.skipUnless(
    connection.features.has_select_for_update,
    "needs a database with row locks; run tests with CIVET_TEST_POSTGRES=1",
)
class Tests(TransactionTestCase):
    """
    Concurrent job_finished requests, each in its own thread and database
    connection. A TransactionTestCase is needed so that the requests'
    transactions really commit and can see each other's changes.
    """

    def setUp(self):
        cache.clear()

    def wait_for_lock_wait(self):
        """
        Waits for another connection to be waiting on a lock.
        """
        with connection.cursor() as cursor:
            for _ in range(200):
                cursor.execute(
                    "SELECT count(*) FROM pg_stat_activity"
                    " WHERE datname = current_database()"
                    " AND wait_event_type = 'Lock'"
                )
                if cursor.fetchone()[0]:
                    return
                time.sleep(0.05)
        self.fail("No request waited on a lock")

    @patch("ci.tasks.job_complete_remote")
    def test_repeated_job_finished(self, mock_task):
        """
        The client sends job_finished again while the first one is still
        running (the first one timed out on the client). The repeated one
        waits for the first to commit, then sees that the job is finished,
        so the Git server is only updated once.
        """
        user = utils.get_test_user()
        job = utils.create_job(user=user)
        utils.create_step_result(job=job)
        client = utils.create_client()
        job.client = client
        job.save()
        url = reverse(
            "ci:client:job_finished", args=[user.build_key, client.name, job.pk]
        )

        # Hold the first request's transaction open until released
        locked = threading.Event()
        release = threading.Event()
        original_save_client_status = views.save_client_status

        def save_client_status(c):
            original_save_client_status(c)
            if not locked.is_set():
                locked.set()
                release.wait(10)

        responses = {}

        def post(name, seconds):
            try:
                data = json.dumps({"seconds": seconds, "complete": True})
                responses[name] = Client().post(
                    url, data, content_type="application/json"
                )
            finally:
                connections.close_all()

        with patch.object(views, "save_client_status", save_client_status):
            first = threading.Thread(target=post, args=("first", 10))
            first.start()
            self.assertTrue(locked.wait(10))
            repeated = threading.Thread(target=post, args=("repeated", 20))
            repeated.start()
            try:
                self.wait_for_lock_wait()
            finally:
                release.set()
                first.join(10)
                repeated.join(10)

        self.assertEqual(responses["first"].status_code, 200)
        self.assertEqual(responses["repeated"].status_code, 200)
        mock_task.enqueue.assert_called_once_with(job.pk, True)
        job.refresh_from_db()
        self.assertTrue(job.complete)
        self.assertEqual(job.seconds.seconds, 10)
