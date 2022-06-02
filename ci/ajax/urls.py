
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
from django.urls import re_path
from . import views

app_name = "ajax"

urlpatterns = [
  re_path(r'^result_output/', views.get_result_output, name='get_result_output'),
  re_path(r'^main_update/', views.main_update, name='main_update'),
  re_path(r'^main_update_html/', views.main_update_html, name='main_update_html'),
  re_path(r'^pr_update/(?P<pr_id>[0-9]+)/$', views.pr_update, name='pr_update'),
  re_path(r'^event_update/(?P<event_id>[0-9]+)/$', views.event_update, name='event_update'),
  re_path(r'^job_results/', views.job_results, name='job_results'),
  re_path(r'^job_results_html/', views.job_results_html, name='job_results_html'),
  re_path(r'^repo_update/', views.repo_update, name='repo_update'),
  re_path(r'^clients/', views.clients_update, name='clients'),
  re_path(r'^(?P<owner>[A-Za-z0-9]+)/(?P<repo>[A-Za-z0-9-_]+)/branches_status',
      views.repo_branches_status, name='repo_branches_status'),
  re_path(r'^(?P<owner>[A-Za-z0-9]+)/(?P<repo>[A-Za-z0-9-_]+)/prs_status', views.repo_prs_status, name='repo_prs_status'),
  re_path(r'^user/(?P<username>[A-Za-z0-9_-]+)/', views.user_open_prs, name='user_open_prs'),
  ]
