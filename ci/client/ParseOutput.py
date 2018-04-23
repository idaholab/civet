
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

from ci import models
import re

def set_job_modules(job, output):
    """
    The output has the following format:
      Currently Loaded Modulefiles:
        1) module1
        2) module2
        ...
      OR
      Currently Loaded Modules:
        1) module1
        2) module2
        ...
    """
    lines_match = re.search(r"(?<=^Currently Loaded Modulefiles:$)(\s+\d+\) (.*))+", output, flags=re.MULTILINE)
    if not lines_match:
        lines_match = re.search(r"(?<=^Currently Loaded Modules:$)(\s+\d+\) (.*))+", output, flags=re.MULTILINE)
        if not lines_match:
            mod_obj, created = models.LoadedModule.objects.get_or_create(name="None")
            job.loaded_modules.add(mod_obj)
            return

    modules = lines_match.group(0)
    # Assume that the module names don't have whitespace. Then "split" will have the module
    # names alternating with the "\d+)"
    mod_list = modules.split()[1::2]
    for mod in mod_list:
        mod_obj, created = models.LoadedModule.objects.get_or_create(name=mod)
        job.loaded_modules.add(mod_obj)

    if not mod_list:
        mod_obj, created = models.LoadedModule.objects.get_or_create(name="None")
        job.loaded_modules.add(mod_obj)

def output_os_search(job, output, name_re, version_re, other_re):
    """
    Search the output for OS information.
    If all the OS information is found then update the job with
    the appropiate record.
    Returns:
      bool: True if the job OS was set, otherwise False
    """
    os_name_match = re.search(name_re, output, flags=re.MULTILINE)
    if not os_name_match:
        return False

    os_name = os_name_match.group(1).strip()
    os_version_match = re.search(version_re, output, flags=re.MULTILINE)
    os_other_match = re.search(other_re, output, flags=re.MULTILINE)
    if os_version_match and os_other_match:
        os_version = os_version_match.group(1).strip()
        os_other = os_other_match.group(1).strip()
        os_record, created = models.OSVersion.objects.get_or_create(name=os_name, version=os_version, other=os_other)
        job.operating_system = os_record
        return True
    return False

def set_job_os(job, output):
    """
    Goes through a series of possible OSes.
    If no match was found then set the job OS to "Other"
    """
    # This matches against the output of "lsb_release -a".
    if output_os_search(job, output, r"^Distributor ID:\s+(.+)$", r"^Release:\s+(.+)$", r"^Codename:\s+(.+)$"):
        return
    # This matches against the output of "systeminfo |grep '^OS'"
    if output_os_search(job, output, r"^OS Name:\s+(.+)$", r"^OS Version:\s+(.+)$", r"^OS Configuration:\s+(.+)$"):
        return
    # This matches against the output of "sw_vers".
    if output_os_search(job, output, r"^ProductName:\s+(.+)$", r"^ProductVersion:\s+(.+)$", r"^BuildVersion:\s+(.+)$"):
        return

    # No OS found
    os_record, created = models.OSVersion.objects.get_or_create(name="Other")
    job.operating_system = os_record

def set_job_stats(job):
    if not job.step_results.exists():
        return
    passed = 0
    failed = 0
    skipped = 0
    for s in job.step_results.all():
        output = "\n".join(s.clean_output().split("<br/>"))
        matches = re.findall(r'>(?P<passed>\d+) passed<.*, .*>(?P<skipped>\d+) skipped<.*, .*>(?P<failed>\d+) failed',
                output, flags=re.IGNORECASE)
        for match in matches:
            passed += int(match[0])
            failed += int(match[2])
            skipped += int(match[1])
    job.test_stats.all().delete()
    if passed or failed or skipped:
        models.JobTestStatistics.objects.create(job=job, passed=passed, failed=failed, skipped=skipped)

def set_job_info(job):
    """
    Sets the modules and OS of the job by scanning the output of
    the first StepResult for the job. It is assumed that all steps
    will have the same modules and OS.
    """
    step_result = job.step_results.first()
    if step_result:
        output = step_result.output
    else:
        output = ""

    job.loaded_modules.clear()
    job.operating_system = None
    set_job_modules(job, output)
    set_job_os(job, output)
    job.save()
    set_job_stats(job)
