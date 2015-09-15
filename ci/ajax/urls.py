from django.conf.urls import url
from . import views

urlpatterns = [
  url(r'^file/', views.get_file, name='get_file'),
  url(r'^result_output/', views.get_result_output, name='get_result_output'),
  url(r'^job_update/', views.job_update, name='job_update'),
  url(r'^events_update/', views.events_update, name='events_update'),
  url(r'^status_update/', views.status_update, name='status_update'),
  url(r'^job_results/', views.job_results, name='job_results'),
  ]
