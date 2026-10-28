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

"""
A test runner for running the tests against a Redis cache, as is done in CI.

The tests clear the cache, which flushes the whole Redis database, so each
parallel test process gets its own database, like it gets its own test
database.
"""

from django.conf import settings
from django.core.cache import caches
from django.test import runner


def _init_worker(counter, *args, **kwargs):
    runner._init_worker(counter, *args, **kwargs)
    # The Redis database of this process; the main process uses the first
    location = settings.CACHES["default"]["LOCATION"].rsplit("/", 1)[0]
    settings.CACHES["default"]["LOCATION"] = "%s/%d" % (location, runner._worker_id)
    # Connect again with the new location
    caches.close_all()
    del caches.settings
    for alias in list(caches):
        del caches[alias]


class RedisParallelTestSuite(runner.ParallelTestSuite):
    init_worker = _init_worker


class RedisTestRunner(runner.DiscoverRunner):
    parallel_test_suite = RedisParallelTestSuite
