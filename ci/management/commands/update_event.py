
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

from django.core.management.base import BaseCommand
from ci import models
from optparse import make_option
import json, random
from ci import event
from django.conf import settings
from django.core.urlresolvers import reverse
import requests

def get_rand():
  return str(random.randint(1, 10000000000))

def get_latest_sha(ev):
  server = ev.base.server()
  auth = server.auth()
  oauth_session = auth.start_session_for_user(ev.build_user)
  last_sha = server.api().last_sha(oauth_session, ev.head.branch.repository.user.name, ev.head.branch.repository.name, ev.head.branch.name)
  if not last_sha:
    return get_rand()
  else:
    return last_sha

def do_post(json_data, base_commit, build_user, base_url):
  out_json = json.dumps(json_data, separators=(',', ': '))
  server = base_commit.server()
  url = ""
  if server.host_type == settings.GITSERVER_GITHUB:
    url = reverse('ci:github:webhook', args=[build_user.build_key])
  elif server.host_type == settings.GITSERVER_GITLAB:
    url = reverse('ci:gitlab:webhook', args=[build_user.build_key])
  url = "%s%s" % (base_url, url)
  print("Posting to URL: %s" % url)
  response = requests.post(url, out_json)
  response.raise_for_status()

class Command(BaseCommand):
  help = 'TESTING ONLY! Grab the event, take the JSON data and change the SHA then post it again to get a new event.'
  option_list = BaseCommand.option_list + (
      make_option('--pk', dest='pk', type='int', help='The event to update'),
      make_option('--url', dest='url', type='str', help='The Civet base URL'),
      make_option('--replace', default=False, action='store_true', dest='replace', help='Delete the event and repost it.'),
  )

  def handle(self, *args, **options):
    ev_pk = options.get('pk')
    url = options.get('url')
    replace = options.get('replace')
    if not url or not ev_pk:
      print("Usage: --pk <event pk> --url <base testing server URL>")
      return
    ev = models.Event.objects.get(pk=ev_pk)
    print("Updating event: %s" % ev)
    settings.REMOTE_UPDATE = False
    settings.INSTALL_WEBHOOK = False
    json_data = json.loads(ev.json_data)
    if replace:
      base_commit = ev.base
      build_user = ev.build_user
      cause = ev.cause
      if cause == models.Event.MANUAL:
        branch = ev.branch
        last_sha = ev.head.sha
        ev.delete()
        me = event.ManualEvent(build_user, branch, last_sha)
      else:
        ev.delete()
        do_post(json_data[0], base_commit, build_user, url)
    else:
      last_sha = get_latest_sha(ev)
      if ev.cause == ev.PULL_REQUEST:
        json_data["pull_request"]["head"]["sha"] = last_sha
        do_post(json_data, ev.base, ev.build_user, url)
      elif ev.cause == ev.PUSH:
        json_data[0]["after"] = last_sha
        json_data[0]["before"] = last_sha
        do_post(json_data[0], ev.base, ev.build_user, url)
      elif ev.cause == ev.MANUAL:
        me = event.ManualEvent(ev.build_user, ev.branch, last_sha)
        me.save()
