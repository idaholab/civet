from django.conf.urls import url
from ci.recipe import views

urlpatterns = [
    url(r'^add/$', views.RecipeCreateView.as_view(), name='add'),
    url(r'^edit/(?P<pk>[0-9]+)/$', views.RecipeUpdateView.as_view(), name='edit'),
    url(r'^delete/(?P<pk>[0-9]+)/$', views.RecipeDeleteView.as_view(), name='delete'),
    url(r'^check/$', views.check_filenames, name='check'),
    url(r'^list_filenames/$', views.list_filenames, name='list_filenames'),
    ]

