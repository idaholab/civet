
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
from django.conf.urls import url, include
from django.http import HttpResponse
from . import views, DebugViews, Stats

app_name = "ci"

urlpatterns = [
    url(r'^$', views.main, name='main'),
    url(r'^branch/(?P<branch_id>[0-9]+)/$', views.view_branch, name='view_branch'),
    url(r'^branch/(?P<owner>[A-Za-z0-9]+)/(?P<repo>[A-Za-z0-9-_]+)/(?P<branch>[A-Za-z0-9-_]+)/$',
        views.view_repo_branch, name='view_repo_branch'),
    url(r'^repo/(?P<repo_id>[0-9]+)/$', views.view_repo, name='view_repo'),
    url(r'^repo/(?P<owner>[A-Za-z0-9]+)/(?P<repo>[A-Za-z0-9-_]+)/$',
        views.view_owner_repo, name='view_owner_repo'),
    url(r'^user/(?P<username>[A-Za-z0-9_-]+)/$', views.view_user, name='view_user'),
    url(r'^event/(?P<event_id>[0-9]+)/$', views.view_event, name='view_event'),
    url(r'^pr/(?P<pr_id>[0-9]+)/$', views.view_pr, name='view_pr'),
    url(r'^job/(?P<job_id>[0-9]+)/$', views.view_job, name='view_job'),
    url(r'^job_results/(?P<job_id>[0-9]+)/$', views.get_job_results, name='job_results'),
    url(r'^view_client/(?P<client_id>[0-9]+)/$', views.view_client, name='view_client'),
    url(r'^recipe_events/(?P<recipe_id>[0-9]+)/$', views.recipe_events, name='recipe_events'),
    url(r'^recipe_crons/(?P<recipe_id>[0-9]+)/$', views.recipe_crons, name='recipe_crons'),
    url(r'^manual_cron/(?P<recipe_id>[0-9]+)/$', views.manual_cron, name='manual_cron'),
    url(r'^cronjobs/$', views.cronjobs, name='cronjobs'),
    url(r'^manual_branch/(?P<build_key>[0-9]+)/(?P<branch_id>[0-9]+)/$',
        views.manual_branch, name='manual_branch'),
    url(r'^manual_branch/(?P<build_key>[0-9]+)/(?P<branch_id>[0-9]+)/(?P<label>[A-Za-z0-9_.-]+)/$',
        views.manual_branch, name='manual_branch'),
    url(r'^invalidate/(?P<job_id>[0-9]+)/$', views.invalidate, name='invalidate'),
    url(r'^invalidate_event/(?P<event_id>[0-9]+)/$', views.invalidate_event, name='invalidate_event'),
    url(r'^profile/(?P<server_type>[0-9]+)/(?P<server_name>[A-Za-z0-9_.-]+)/$',
        views.view_profile, name='view_profile'),
    url(r'^activate_job/(?P<job_id>[0-9]+)/$', views.activate_job, name='activate_job'),
    url(r'^activate_event/(?P<event_id>[0-9]+)/$', views.activate_event, name='activate_event'),
    url(r'^cancel_job/(?P<job_id>[0-9]+)/$', views.cancel_job, name='cancel_job'),
    url(r'^cancel_event/(?P<event_id>[0-9]+)/$', views.cancel_event, name='cancel_event'),
    url(r'^job_info_search/', views.job_info_search, name='job_info_search'),
    url(r'^user_repo_settings/', views.user_repo_settings, name='user_repo_settings'),
    url(r'^(?P<owner>[A-Za-z0-9]+)/(?P<repo>[A-Za-z0-9-_]+)/(?P<branch>[A-Za-z0-9-_]+)/branch_status.svg',
        views.repo_branch_status, name='repo_branch_status'),
    url(r'^(?P<branch_id>[0-9]+)/branch_status.svg', views.branch_status, name='branch_status'),
    url(r'^events/', views.event_list, name='event_list'),
    url(r'^sha_events/(?P<owner>[A-Za-z0-9_-]+)/(?P<repo>[A-Za-z0-9-_]+)/(?P<sha>[A-Za-z0-9-_]+)/$',
        views.sha_events, name='sha_events'),
    url(r'^num_tests/', Stats.num_tests, name='num_tests'),
    url(r'^num_prs/', Stats.num_prs_by_repo, name='num_prs'),
    url(r'^pullrequests/', views.pr_list, name='pullrequest_list'),
    url(r'^branches/', views.branch_list, name='branch_list'),
    url(r'^clients/', views.client_list, name='client_list'),
    url(r'^mooseframework/', views.mooseframework, name='mooseframework'),
    url(r'^scheduled/', views.scheduled_events, name='scheduled'),
    url(r'^github/', include('ci.github.urls')),
    url(r'^gitlab/', include('ci.gitlab.urls')),
    url(r'^bitbucket/', include('ci.bitbucket.urls')),
    url(r'^client/', include('ci.client.urls')),
    url(r'^ajax/', include('ci.ajax.urls')),
    url(r'^robots.txt$', lambda r: HttpResponse("User-agent: *\nDisallow: /", content_type="text/plain")),
    ]

# URLs used for debugging
urlpatterns.append(url(r'^start_session/(?P<user_id>[0-9]+)/$',
    DebugViews.start_session, name='start_session') )
urlpatterns.append(url(r'^start_session_by_name/(?P<name>[0-9a-z]+)/$',
    DebugViews.start_session_by_name, name='start_session_by_name'))
urlpatterns.append(url(r'^job_script/(?P<job_id>[0-9]+)/$', DebugViews.job_script, name='job_script'))
