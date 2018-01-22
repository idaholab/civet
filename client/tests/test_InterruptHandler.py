
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
from django.test import override_settings
from ci.tests import utils as test_utils
from client import InterruptHandler
import signal, os, subprocess
from queue import Queue

@override_settings(INSTALLED_GITSERVERS=[test_utils.github_config()])
class InterruptHandlerTests(SimpleTestCase):
    def test_handler(self):
        q = Queue()
        i = InterruptHandler.InterruptHandler(q, sig=[signal.SIGUSR1])
        i.set_message("hi")
        self.assertEqual(i.triggered, False)

        script = "sleep 1 && kill -USR1 %s" % os.getpid()
        proc = subprocess.Popen(script, shell=True, executable="/bin/bash", stdout=subprocess.PIPE)
        proc.wait()
        self.assertEqual(i.triggered, True)
        self.assertEqual(q.qsize(), 1)
        msg = q.get(block=False)
        self.assertEqual(msg, "hi")
