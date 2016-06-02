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

def do_post(json_data, ev, base_url):
  out_json = json.dumps(json_data, separators=(',', ': '))
  server = ev.base.server()
  url = ""
  if server.host_type == settings.GITSERVER_GITHUB:
    url = reverse('ci:github:webhook', args=[ev.build_user.build_key])
  elif server.host_type == settings.GITSERVER_GITLAB:
    url = reverse('ci:gitlab:webhook', args=[ev.build_user.build_key])
  url = "%s%s" % (base_url, url)
  print("Posting to URL: %s" % url)
  response = requests.post(url, out_json)
  response.raise_for_status()

class Command(BaseCommand):
  help = 'TESTING ONLY! Grab the event, take the JSON data and change the SHA then post it again to get a new event.'
  option_list = BaseCommand.option_list + (
      make_option('--pk', dest='pk', type='int', help='The event to update'),
      make_option('--url', dest='url', type='str', help='The Civet base URL'),
  )

  def handle(self, *args, **options):
    ev_pk = options.get('pk')
    url = options.get('url')
    if not url or not ev_pk:
      print("Usage: --pk <event pk> --url <base testing server URL>")
      return
    ev = models.Event.objects.get(pk=ev_pk)
    print("Updating event: %s" % ev)
    settings.REMOTE_UPDATE = False
    settings.INSTALL_WEBHOOK = False
    json_data = json.loads(ev.json_data)
    last_sha = get_latest_sha(ev)
    if ev.cause == ev.PULL_REQUEST:
      json_data["pull_request"]["head"]["sha"] = last_sha
      do_post(json_data, ev, url)
    elif ev.PUSH:
      json_data["after"] = last_sha
      do_post(json_data, ev, url)
    elif ev.MANUAL:
      me = event.ManualEvent(ev.build_user, ev.branch, last_sha)
      me.save()
