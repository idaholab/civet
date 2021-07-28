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
import logging
from ci import models, views, event
from django.urls import reverse
logger = logging.getLogger('ci')

class PushEvent(object):
    """
    Holds all the data that will go into a Event of
    a Push type. Will create and save the DB tables.
    The creator of this object will need to set the following:
      base_commit : GitCommitData of the base sha
      head_commit : GitCommitData of the head sha
      comments_url : Url to the comments
      full_text : All the payload data
      build_user : GitUser corresponding to the build user
      description : Description of the push, ie "Merge commit blablabla"
    Then calling save() will actually create the tables.
    """
    def __init__(self):
        self.base_commit = None
        self.head_commit = None
        self.comments_url = None
        self.full_text = None
        self.build_user = None
        self.description = ''
        self.changed_files = []

    def save(self):
        logger.info('New push event on {}/{} for {}'.format(self.base_commit.repo, self.base_commit.ref, self.build_user))
        default_recipes = models.Recipe.objects.filter(
            active = True,
            current = True,
            branch__repository__user__server = self.base_commit.server,
            branch__repository__user__name = self.base_commit.owner,
            branch__repository__name = self.base_commit.repo,
            branch__name = self.base_commit.ref,
            build_user = self.build_user,
            cause = models.Recipe.CAUSE_PUSH,
            ).order_by("-priority", "display_name")

        if not default_recipes:
            logger.info('No recipes for push on {}/{} for {}'.format(self.base_commit.repo,
                self.base_commit.ref,
                self.build_user))
            return

        # create this after so we don't create unnecessary commits
        base = self.base_commit.create()
        head = self.head_commit.create()

        base.branch.repository.active = True
        base.branch.repository.save()

        ev, created = models.Event.objects.get_or_create(
            build_user=self.build_user,
            head=head,
            base=base,
            cause=models.Event.PUSH,
            )
        recipes = []
        if not created:
            # This is just an update to the event. We don't want to create new recipes, just
            # use the ones already loaded.
            for j in ev.jobs.all():
                recipes.append(j.recipe)
        else:
            recipes = [r for r in default_recipes.all()]
            if ev.auto_cancel_event_except_current():
                self._auto_cancel_events(ev)
            else:
                self._auto_cancel_jobs(ev, recipes)

        ev.comments_url = self.comments_url
        ev.set_json_data(self.full_text)
        ev.description = self.description
        ev.set_changed_files(self.changed_files)
        ev.save()
        self._process_recipes(ev, recipes)

    def _process_recipes(self, ev, recipes):
        for r in recipes:
            if not r.active:
                continue
            for config in r.build_configs.order_by("name").all():
                job, created = models.Job.objects.get_or_create(recipe=r, event=ev, config=config)
                if created:
                    job.active = True
                    if r.automatic == models.Recipe.MANUAL:
                        job.active = False
                        job.status = models.JobStatus.ACTIVATION_REQUIRED
                    job.ready = False
                    job.complete = False
                    job.save()
                    logger.info('Created job {}: {}: on {}'.format(job.pk, job, r.repository))
        ev.make_jobs_ready()

    def _auto_cancel_jobs(self, ev, recipes):
        # if a recipe has auto_cancel_on_push then we need to cancel any jobs
        # on the same branch that are currently running
        cancel_job_states = [models.JobStatus.NOT_STARTED, models.JobStatus.RUNNING]
        ev_url = reverse('ci:view_event', args=[ev.pk])
        msg = "Canceled due to new push <a href='%s'>event</a>" % ev_url
        for r in recipes:
            if r.auto_cancel_on_push:
                js = models.Job.objects.filter(
                        status__in=cancel_job_states,
                        recipe__branch=r.branch,
                        recipe__cause=r.cause,
                        recipe__build_user=r.build_user,
                        recipe__filename=r.filename,
                        )
                for j in js.all():
                    logger.info('Job {}: {} canceled by new push event {}: {}'.format(j.pk, j, ev.pk, ev))
                    # We don't need to update remote Git server status since
                    # we will have new jobs
                    views.set_job_canceled(j, msg)
                    j.event.set_status()
                    j.event.set_complete_if_done()
        ev.save() # update the timestamp so the js updater works


    def _auto_cancel_events(self, ev):
        base_q = models.Event.objects.filter(build_user=ev.build_user,
            base__branch=ev.base.branch,
            cause=models.Event.PUSH,
            )
        ev_url = reverse('ci:view_event', args=[ev.pk])
        msg = "Canceled due to new push <a href='%s'>event</a>" % ev_url

        # First see if there is a running event. If so, then we need to cancel all events in between
        # that one and this one.
        # If not, then just cancel any previous events that are not complete
        current_running = base_q.filter(status=models.JobStatus.RUNNING).order_by('-created')
        running_event = None
        if current_running.count() > 0:
            running_event = current_running.last()
            cancel_events = base_q.filter(complete=False, created__gt=running_event.created, created__lt=ev.created)
            for e in cancel_events.all():
                event.auto_cancel_event(e, msg)
        else:
            old_events = base_q.filter(status=models.JobStatus.NOT_STARTED).exclude(pk=ev.pk)
            for e in old_events.all():
                event.auto_cancel_event(e, msg)

