from django.conf.urls import url, include
from . import views

urlpatterns = [
    url(r'^$', views.main, name='main'),
    url(r'^branch/(?P<branch_id>[0-9]+)/$', views.view_branch, name='view_branch'),
    url(r'^repo/(?P<repo_id>[0-9]+)/$', views.view_repo, name='view_repo'),
    url(r'^event/(?P<event_id>[0-9]+)/$', views.view_event, name='view_event'),
    url(r'^pr/(?P<pr_id>[0-9]+)/$', views.view_pr, name='view_pr'),
    url(r'^job/(?P<job_id>[0-9]+)/$', views.view_job, name='view_job'),
    url(r'^job_results/(?P<job_id>[0-9]+)/$', views.get_job_results, name='job_results'),
    url(r'^view_client/(?P<client_id>[0-9]+)/$', views.view_client, name='view_client'),
    url(r'^recipe_events/(?P<recipe_id>[0-9]+)/$', views.recipe_events, name='recipe_events'),
    url(r'^manual_branch/(?P<build_key>[0-9]+)/(?P<branch_id>[0-9]+)/$', views.manual_branch, name='manual_branch'),
    url(r'^invalidate/(?P<job_id>[0-9]+)/$', views.invalidate, name='invalidate'),
    url(r'^invalidate_event/(?P<event_id>[0-9]+)/$', views.invalidate_event, name='invalidate_event'),
    url(r'^profile/(?P<server_type>[0-9]+)/$', views.view_profile, name='view_profile'),
    url(r'^activate_job/(?P<job_id>[0-9]+)/$', views.activate_job, name='activate_job'),
    url(r'^cancel_job/(?P<job_id>[0-9]+)/$', views.cancel_job, name='cancel_job'),
    url(r'^cancel_event/(?P<event_id>[0-9]+)/$', views.cancel_event, name='cancel_event'),
    url(r'^events/', views.event_list, name='event_list'),
    url(r'^pullrequests/', views.pr_list, name='pullrequest_list'),
    url(r'^branches/', views.branch_list, name='branch_list'),
    url(r'^clients/', views.client_list, name='client_list'),
    url(r'^mooseframework/', views.mooseframework, name='mooseframework'),
    url(r'^github/', include('ci.github.urls', namespace='github')),
    url(r'^gitlab/', include('ci.gitlab.urls', namespace='gitlab')),
    url(r'^bitbucket/', include('ci.bitbucket.urls', namespace='bitbucket')),
    url(r'^client/', include('ci.client.urls', namespace='client')),
    url(r'^ajax/', include('ci.ajax.urls', namespace='ajax')),
    url(r'^recipe/', include('ci.recipe.urls', namespace='recipe')),
    ]

urlpatterns.append(url(r'^start_session/(?P<user_id>[0-9]+)/$', views.start_session, name='start_session') )
urlpatterns.append(url(r'^start_session_by_name/(?P<name>[0-9a-z]+)/$', views.start_session_by_name, name='start_session_by_name'))
urlpatterns.append(url(r'^job_script/(?P<job_id>[0-9]+)/$', views.job_script, name='job_script'))
