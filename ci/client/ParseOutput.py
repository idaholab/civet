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
from ci import models
import re


# A single count token (e.g. ">123 passed") in ansi2html output. Scanned with
# one linear pass; step output is attacker-controlled, so nothing here may
# backtrack.
_STAT_TOKEN = re.compile(r">(\d+) (passed|skipped|failed)", flags=re.IGNORECASE)
_STAT_ORDER = ("passed", "skipped", "failed")


def _parse_line_stats(line):
    """
    Returns a list of (passed, skipped, failed) tuples found in a single line
    of output, where each tuple is a passed, skipped, then failed count in order.
    """
    found = []
    counts = {}
    for match in _STAT_TOKEN.finditer(line):
        kind = match.group(2).lower()
        if kind == _STAT_ORDER[0]:
            counts = {}
        elif not counts or kind != _STAT_ORDER[len(counts)]:
            continue
        counts[kind] = int(match.group(1))
        if len(counts) == len(_STAT_ORDER):
            found.append(tuple(counts[k] for k in _STAT_ORDER))
            counts = {}
    return found


def set_job_stats(job):
    if not job.step_results.exists():
        return
    passed = 0
    failed = 0
    skipped = 0
    for s in job.step_results.all():
        for line in s.clean_output().split("<br/>"):
            for line_passed, line_skipped, line_failed in _parse_line_stats(line):
                passed += line_passed
                skipped += line_skipped
                failed += line_failed
    job.test_stats.all().delete()
    if passed or failed or skipped:
        models.JobTestStatistics.objects.create(
            job=job, passed=passed, failed=failed, skipped=skipped
        )


def set_job_info(job):
    """
    Set job information by parsing the job output.
    """
    set_job_stats(job)
