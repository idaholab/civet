
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


from django.core.management.base import BaseCommand, CommandError
from ci import models
from optparse import make_option

class Command(BaseCommand):
    help = 'Show the repos accessible by <user> that are owned by <master>'
    option_list = BaseCommand.option_list + (
        make_option('--master', default=None, dest='master', type='str',
            help='Specifies the user who owns the repos. This user should have logged in and have a token'),
        make_option('--user', default=None, dest='user', type='str',
            help='User to check against'),
        )

    def handle(self, *args, **options):
      master = options.get("master", None)
      user = options.get("user", None)
      if not master:
        raise CommandError("Need to specify master")

      master_rec = models.GitUser.objects.get(name=master)
      if not master_rec.token:
        raise CommandError("%s doesn't have a token set" % master_rec)
      auth_session = master_rec.start_session()
      api = master_rec.server.api()
      repos = api.get_all_repos(auth_session, master)
      if not user:
        print("User %s can access:\n%s" % (master, '\n'.join(repos)))
      else:
        user_rec, user_created = models.GitUser.objects.get_or_create(name=user, server=master_rec.server)
        all_repos = []
        for repo in repos:
          owner_name, repo_name = repo.split("/")
          print("Checking %s/%s" % (owner_name, repo_name))
          owner_rec, owner_created = models.GitUser.objects.get_or_create(name=owner_name, server=master_rec.server)
          repo_rec, repo_created = models.Repository.objects.get_or_create(name=repo_name, user=owner_rec)
          if api.is_collaborator(auth_session, user_rec, repo_rec):
            all_repos.append(repo)
          if repo_created:
            repo_rec.delete()
          if owner_created:
            owner_rec.delete()
        if user_created:
          user_rec.delete()
        print("User %s can access:\n%s" % (user, '\n'.join(all_repos)))
