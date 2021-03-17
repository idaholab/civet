
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
from django import template
from django.conf import settings
from django.urls import reverse

register = template.Library()

# Sanitized INSTALLED_GITSERVERS
@register.simple_tag
def installed_gitservers(request):
    gitservers = []
    for s in settings.INSTALLED_GITSERVERS:
        d = {"type": s["type"],
                "hostname": s["hostname"],
                "icon_class": s["icon_class"],
                "html_url": s["html_url"],
                "displayname" : ""
                }
        if "login_label" in s.keys():
            d["displayname"] = s["login_label"]
        if s["type"] == settings.GITSERVER_GITHUB:
            d["sign_in"] = reverse("ci:github:sign_in", args=[s["hostname"]])
            d["sign_out"] = reverse("ci:github:sign_out", args=[s["hostname"]])
            d["description"] = "GitHub"
        elif s["type"] == settings.GITSERVER_GITLAB:
            d["sign_in"] = reverse("ci:gitlab:sign_in", args=[s["hostname"]])
            d["sign_out"] = reverse("ci:gitlab:sign_out", args=[s["hostname"]])
            d["description"] = "GitLab"
        elif s["type"] == settings.GITSERVER_BITBUCKET:
            d["sign_in"] = reverse("ci:bitbucket:sign_in", args=[s["hostname"]])
            d["sign_out"] = reverse("ci:bitbucket:sign_out", args=[s["hostname"]])
            d["description"] = "BitBucket"

        user_key = "%s__user" % s["hostname"]
        d["user"] = request.session.get(user_key, "")

        gitservers.append(d)
    return gitservers
