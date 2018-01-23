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
from . import models
import logging
logger = logging.getLogger('ci')

class ReleaseEvent(object):
    """
    Holds all the data that will go into a Event of
    a Release type. Will create and save the DB tables.
    The creator of this object will need to set the following:
      base_commit : GitCommitData of the base sha
      head_commit : GitCommitData of the head sha
      release_tag: Tag of the release
      full_text : All the payload data
      build_user : GitUser corresponding to the build user
      description : Description of the release, ie "Merge commit blablabla"
    Then calling save() will actually create the tables.
    """
    def __init__(self):
        self.commit = None
        self.full_text = None
        self.build_user = None
        self.description = ''
        self.release_tag = ''

    def save(self, request):
        logger.info("New release event '{}' on {}/{}:{} for {}".format(
            self.release_tag,
            self.commit.owner,
            self.commit.repo,
            self.commit.ref,
            self.build_user))

        recipes = models.Recipe.objects.filter(
            active = True,
            current = True,
            repository__user__server = self.commit.server,
            repository__user__name = self.commit.owner,
            repository__name = self.commit.repo,
            build_user = self.build_user,
            cause = models.Recipe.CAUSE_RELEASE,
            )

        if not recipes:
            logger.info('No recipes for release {} on {}/{} for {}'.format(
                self.release_tag, self.commit.repo, self.commit.ref, self.build_user))
            return

        # create this after so we don't create unnecessary commits
        base = self.commit.create()

        ev, created = models.Event.objects.get_or_create(
            build_user=self.build_user,
            head=base,
            base=base,
            cause=models.Event.RELEASE,
            )

        ev.set_json_data(self.full_text)
        ev.description = self.description
        ev.save()
        self._process_recipes(ev, recipes)

    def _process_recipes(self, ev, recipes):
        for r in recipes.all():
            if not r.active:
                continue
            for config in r.build_configs.all():
                job, created = models.Job.objects.get_or_create(recipe=r, event=ev, config=config)
                if created:
                    job.active = True
                    if r.automatic == models.Recipe.MANUAL:
                        job.active = False
                    job.ready = False
                    job.complete = False
                    job.save()
                    logger.info('Created job {}: {}: on {}'.format(job.pk, job, r.repository))
        ev.make_jobs_ready()
