
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

"""
This file will be sourced by the INL client.
Separated out for easier upgrades of the client.
Besides the required settings, you can do any valid ptyhon
to setup the required environment.
REQUIRED:
  SERVERS: a list of servers
OPTIONAL:
  MANAGE_BUILD_ROOT: True to create/clear BUILD_ROOT for each job
"""

"""
A list of servers to poll.
Each server is tuple:
  url: URL to the server, eg https://localhost
  build_key: Build key assigned by the CIVET server for a user
  certificate: Path to the certificate of the server. If False
              then SSL cert verification is not done.
"""
SERVERS = [('server0', 'build_key', False), ]

NUM_CLIENTS = 1

"""
True to create/clear BUILD_ROOT for each job.
"""
MANAGE_BUILD_ROOT = False
