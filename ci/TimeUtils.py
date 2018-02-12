
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

from django.contrib.humanize.templatetags.humanize import naturaltime
from django.utils import timezone
import datetime, math

def sortable_time_str(d):
    return d.strftime('%Y%m%d%H%M%S%f')

def display_time_str(d):
    #return d.strftime('%H:%M:%S %m/%d/%y')
    return naturaltime(d)

def human_time_str(d):
    #return d.strftime('%H:%M:%S %m/%d/%y')
    return naturaltime(d)

def get_local_timestamp():
    return math.floor((timezone.localtime(timezone.now()) - timezone.make_aware(datetime.datetime.fromtimestamp(0))).total_seconds())

def get_local_time():
    return timezone.localtime(timezone.now())

def std_time_str(d):
    return d.strftime('%H:%M:%S %m/%d/%y')
