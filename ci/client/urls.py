from django.conf.urls import url
from . import views

urlpatterns = [
  url(r'^claim_job/(?P<build_key>[0-9]+)/(?P<config_name>[-\w]+)/(?P<client_name>[-\w]+)/$', views.claim_job, name='claim_job'),
  url(r'^ready_jobs/(?P<build_key>[0-9]+)/(?P<config_name>[-\w]+)/(?P<client_name>[-\w]+)/$', views.ready_jobs, name='ready_jobs'),
  url(r'^job_finished/(?P<build_key>[0-9]+)/(?P<client_name>[-\w]+)/(?P<job_id>[0-9]+)/$', views.job_finished, name='job_finished'),
  url(r'^update_step_result/(?P<build_key>[0-9]+)/(?P<client_name>[-\w]+)/(?P<stepresult_id>[0-9]+)/$', views.update_step_result, name='update_step_result'),
  ]

