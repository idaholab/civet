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
    help = 'Disable a repo. Mark all of its PRs as closed. Mark all its branches as inactive'
    option_list = BaseCommand.option_list + (
        make_option('--repo', default=None, dest='repo', type='str', help='The repository name'),
        make_option('--owner', default=None, dest='owner', type='str', help='Owner of the repo'),
        make_option('--dry-run', default=False, dest='dryrun', action='store_true', help='Just show what would be changed'),
        )

    def handle(self, *args, **options):
        repo = options.get("repo", None)
        owner = options.get("owner", None)
        dryrun = options.get("dryrun", None)
        dryrun_str = ""
        if dryrun:
            dryrun_str = "DRYRUN: "
        if not owner:
            raise CommandError("Need to specify owner")
        if not repo:
            raise CommandError("Need to specify repository")

        owner_rec = models.GitUser.objects.get(name=owner)
        repo_rec = models.Repository.objects.get(user=owner_rec, name=repo)

        active_branches = models.Branch.objects.filter(repository=repo_rec).exclude(status=models.JobStatus.NOT_STARTED)
        for b in active_branches.all():
            print("%sMarking branch %s inactive" % (dryrun_str, b))
            if not dryrun:
                b.status = models.JobStatus.NOT_STARTED
                b.save()

        open_prs = models.PullRequest.objects.filter(repository=repo_rec, closed=False)
        for p in open_prs.all():
            print("%sClosing PR %s" % (dryrun_str, p))
            if not dryrun:
                p.closed = True
                p.save()
