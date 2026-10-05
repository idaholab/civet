# Copyright 2016-2025 Battelle Energy Alliance, LLC
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
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q
from ci import models


class Command(BaseCommand):
    help = (
        "Remove a repo along with all of its branches, PRs, events, recipes, and jobs."
        " The repo must not have any active recipes."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--repo", default=None, dest="repo", help="The repository name"
        )
        parser.add_argument(
            "--owner", default=None, dest="owner", help="Owner of the repo"
        )
        parser.add_argument(
            "--dry-run",
            default=False,
            dest="dryrun",
            action="store_true",
            help="Just show what would be removed",
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

        try:
            owner_rec = models.GitUser.objects.get(name=owner)
        except models.GitUser.DoesNotExist:
            raise CommandError("Invalid username: %s" % owner)
        try:
            repo_rec = models.Repository.objects.get(user=owner_rec, name=repo)
        except models.Repository.DoesNotExist:
            raise CommandError("Invalid repository: %s/%s" % (owner, repo))

        active_recipes = models.Recipe.objects.filter(repository=repo_rec, active=True)
        if active_recipes.exists():
            names = "\n".join(
                "  %s (%s)" % (r.name, r.filename)
                for r in active_recipes.order_by("name")
            )
            raise CommandError(
                "Repository %s has %s active recipe(s):\n%s"
                % (repo_rec, active_recipes.count(), names)
            )

        # Deleting the repo cascades to every event with a head or base commit in it.
        # An event whose base is in another repo (ie a PR from this fork) belongs
        # to that other repo, so don't silently delete it.
        events = models.Event.objects.filter(
            Q(head__branch__repository=repo_rec) | Q(base__branch__repository=repo_rec)
        )
        other_events = events.exclude(base__branch__repository=repo_rec)
        if other_events.exists():
            other_repos = sorted(set(str(e.base.repo()) for e in other_events))
            raise CommandError(
                "Repository %s has %s event(s) that belong to other repositories: %s"
                % (repo_rec, other_events.count(), ", ".join(other_repos))
            )

        recipes = models.Recipe.objects.filter(repository=repo_rec)
        jobs = models.Job.objects.filter(Q(event__in=events) | Q(recipe__in=recipes))
        self.stdout.write("%sRemoving repository %s" % (dryrun_str, repo_rec))
        self.stdout.write("  Branches: %s" % repo_rec.branches.count())
        self.stdout.write("  Pull requests: %s" % repo_rec.pull_requests.count())
        self.stdout.write("  Events: %s" % events.count())
        self.stdout.write("  Recipes: %s" % recipes.count())
        self.stdout.write("  Jobs: %s" % jobs.count())

        if not dryrun:
            total, per_model = repo_rec.delete()
            self.stdout.write("Removed %s objects:" % total)
            for name, count in sorted(per_model.items()):
                self.stdout.write("  %s: %s" % (name, count))
