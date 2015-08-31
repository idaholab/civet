from django.conf.urls import url
from ci.gitlab import oauth, views

urlpatterns = [
  url(r'^sign_in/', oauth.sign_in, name='sign_in'),
  url(r'^sign_out/', oauth.sign_out, name='sign_out'),
  url(r'^webhook/(?P<build_key>[0-9]+)/$', views.webhook, name='webhook'),
  ]
