
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
import signal

class InterruptHandler(object):
    def __init__(self, message_q, sig=[]):
        self.sig = sig
        self.message_q = message_q
        self.message = None
        self.triggered = False

        self.orig_handler = {}
        for sig in self.sig:
            self.orig_handler[sig] = signal.getsignal(sig)

        def handler(signum, sigframe):
            if self.message:
                self.message_q.put(self.message)
            self.triggered = True

        for sig in self.sig:
            signal.signal(sig, handler)

    def set_message(self, msg):
        self.message = msg

# This can be used if you need to use this with "with"
#  def __exit__(self, type, value, tb):
#    for sig in self.sig:
#      signal.signal(sig, self.original_handler[sig])
