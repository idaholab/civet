
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

from __future__ import unicode_literals, absolute_import
from django.urls import path, re_path
from . import views

app_name = "client"

urlpatterns = [
  path('get_job/', views.get_job, name='get_job'),
  re_path(r'^job_finished/(?P<build_key>[0-9]+)/(?P<client_name>[-\w.]+)/(?P<job_id>[0-9]+)/$',
      views.job_finished, name='job_finished'),
  re_path(r'^update_step_result/(?P<build_key>[0-9]+)/(?P<client_name>[-\w.]+)/(?P<stepresult_id>[0-9]+)/$',
      views.update_step_result, name='update_step_result'),
  re_path(r'^start_step_result/(?P<build_key>[0-9]+)/(?P<client_name>[-\w.]+)/(?P<stepresult_id>[0-9]+)/$',
      views.start_step_result, name='start_step_result'),
  re_path(r'^complete_step_result/(?P<build_key>[0-9]+)/(?P<client_name>[-\w.]+)/(?P<stepresult_id>[0-9]+)/$',
      views.complete_step_result, name='complete_step_result'),
  re_path(r'^ping/(?P<client_name>[-\w.]+)/$', views.client_ping, name='client_ping'),
  re_path(r'^update_remote_job_status/(?P<job_id>[0-9]+)/$', views.update_remote_job_status, name='update_remote_job_status'),
  ]
