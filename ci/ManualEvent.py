
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
from ci import models, GitCommitData
import logging
logger = logging.getLogger('ci')

class ManualEvent(object):
    """
    A manual event. This is typically called
    by cron or something similar.
    """
    def __init__(self, build_user, branch, latest, activate_label="", recipe=None):
        """
        Constructor for ManualEvent.
        Input:
          build_user: models.GitUser of the build user
          branch: A models.Branch on which to run the event on.
          latest: str: The latest SHA on the branch
        """
        self.recipe = recipe
        self.user = build_user
        self.branch = branch
        self.latest = latest
        self.force = False
        self.activate_label = activate_label
        self.description = ''

    def save(self, update_branch_status=True):
        """
        Create the tables in the DB and make any jobs ready.
        """
        base_commit = GitCommitData.GitCommitData(
            self.branch.repository.user.name,
            self.branch.repository.name,
            self.branch.name,
            self.latest,
            "",
            self.branch.repository.user.server,
            )
        base = base_commit.create()

        recipes = [self.recipe]
        if self.recipe is None:
            recipes = models.Recipe.objects.filter(active=True,
                    current=True,
                    build_user=self.user,
                    branch=base.branch,
                    cause=models.Recipe.CAUSE_MANUAL,
                    activate_label=self.activate_label,
                    ).order_by('-priority', 'display_name').all()

        if not recipes:
            if self.activate_label:
                logger.info("No manual recipes on %s for %s with label '%s'" % (
                    base.branch, self.user, self.activate_label))
            else:
                logger.info("No manual recipes on %s for %s" % (base.branch, self.user))
            base_commit.remove()
            return

        self.branch.repository.active = True
        self.branch.repository.save()

        ev, created = models.Event.objects.get_or_create(build_user=self.user,
                head=base,
                base=base,
                cause=models.Event.MANUAL,
                duplicates=0)

        if created:
            ev.complete = False
            ev.update_branch_status = update_branch_status
            ev.description = '(scheduled)'
            ev.save()
            logger.info("Created manual event on %s for %s" % (self.branch, self.user))
        elif self.force:
            last_ev = models.Event.objects.filter(build_user=self.user,
                    head=base,
                    base=base,
                    cause=models.Event.MANUAL,
                    ).order_by('duplicates').last()
            duplicate = last_ev.duplicates + 1
            ev = models.Event.objects.create(build_user=self.user,
                    head=base,
                    base=base,
                    cause=models.Event.MANUAL,
                    duplicates=duplicate)
            ev.complete = False
            ev.update_branch_status = update_branch_status
            ev.description = '(forced scheduled)'
            ev.save()
            logger.info("Created duplicate scheduled event #%s on %s for %s" % (duplicate, self.branch, self.user))
        else:
            logger.info("Scheduled event on %s for %s already exists: %s" % (self.branch, self.user, ev))

        self._process_recipes(ev, recipes)

    def _process_recipes(self, ev, recipes):
        """
        Create jobs based on the recipes.
        Input:
          ev: models.Event
          recipes: Iterable of recipes to process.
        """
        existing_recipes = []
        for j in ev.jobs.all():
            existing_recipes.append(j.recipe.filename)

        for r in recipes:
            if r.filename in existing_recipes or not r.active:
                # We don't want to mess around with any jobs that have the same recipe
                # (or other versions of the recipe)
                continue
            for config in r.build_configs.order_by("name").all():
                job, created = models.Job.objects.get_or_create(recipe=r, event=ev, config=config)
                if created:
                    job.ready = False
                    job.complete = False
                    if r.automatic == models.Recipe.MANUAL:
                        job.active = False
                        job.status = models.JobStatus.ACTIVATION_REQUIRED
                    job.save()
                    logger.info('Created job {}: {} on {}'.format(job.pk, job, r.repository))

        ev.make_jobs_ready()
