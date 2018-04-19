
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

from __future__ import unicode_literals
from django.conf.urls import url
from ci.bitbucket import oauth, views

app_name = "bitbucket"

urlpatterns = [
  url(r'^sign_in/(?P<host>[a-zA-Z0-9_.-]+)/', oauth.sign_in, name='sign_in'),
  url(r'^sign_out/(?P<host>[a-zA-Z0-9_.-]+)/', oauth.sign_out, name='sign_out'),
  url(r'^callback/(?P<host>[a-zA-Z0-9_.-]+)/', oauth.callback, name='callback'),
  url(r'^webhook/(?P<build_key>[0-9]+)/$', views.webhook, name='webhook'),
  ]
