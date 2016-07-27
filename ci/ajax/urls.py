
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

from django.conf.urls import url
from . import views

urlpatterns = [
  url(r'^result_output/', views.get_result_output, name='get_result_output'),
  url(r'^main_update/', views.main_update, name='main_update'),
  url(r'^main_update_html/', views.main_update_html, name='main_update_html'),
  url(r'^pr_update/(?P<pr_id>[0-9]+)/$', views.pr_update, name='pr_update'),
  url(r'^event_update/(?P<event_id>[0-9]+)/$', views.event_update, name='event_update'),
  url(r'^job_results/', views.job_results, name='job_results'),
  url(r'^job_results_html/', views.job_results_html, name='job_results_html'),
  url(r'^repo_update/', views.repo_update, name='repo_update'),
  url(r'^clients/', views.clients_update, name='clients'),
  ]
