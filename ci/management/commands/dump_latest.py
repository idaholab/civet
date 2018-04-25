
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
from django.core.management.base import BaseCommand
from ci import models
from django.core import serializers

class Command(BaseCommand):
    help = 'Dump all the DB tables required to make a good test DB.'
    def add_arguments(self, parser):
        parser.add_argument('--indent', default=2, dest='indent', type=int,
            help='Specifies the indent level to use when pretty-printing output')
        parser.add_argument('--out', dest='output', default='out.json', help='Output file to use')
        parser.add_argument('--num', dest='num', type=int, default=40, help='Number of events to dump')

    def add_obj(self, rec, collected):
        if not rec:
            return
        if rec not in collected:
            collected.append(rec)

    def add_query(self, q, collected):
        for tmp in q.all():
            self.add_obj(tmp, collected)

    def add_event(self, e, collected):
        if e in collected:
            return
        self.add_obj(e, collected)
        self.add_obj(e.base.branch.repository.user.server, collected)
        self.add_obj(e.base.branch.repository.user, collected)
        self.add_obj(e.base.branch.repository, collected)
        self.add_obj(e.base.branch, collected)
        self.add_obj(e.base, collected)
        self.add_obj(e.head.branch.repository.user.server, collected)
        self.add_obj(e.head.branch.repository.user, collected)
        self.add_obj(e.head.branch.repository, collected)
        self.add_obj(e.head.branch, collected)
        self.add_obj(e.head, collected)
        self.add_obj(e.build_user, collected)
        if e.pull_request:
            self.add_obj(e.pull_request, collected)
            for recipe in e.pull_request.alternate_recipes.all():
                self.add_obj(recipe, collected)

        for j in e.jobs.all():
            self.add_obj(j, collected)
            self.add_obj(j.client, collected)
            self.add_obj(j.config, collected)
            self.add_obj(j.operating_system, collected)
            self.add_query(j.loaded_modules, collected)
            self.add_obj(j.recipe, collected)
            self.add_query(j.recipe.depends_on, collected)
            self.add_query(j.recipe.environment_vars, collected)
            self.add_query(j.recipe.prestepsources, collected)
            self.add_query(j.changelog, collected)
            self.add_query(j.recipe.steps, collected)
            for tmp in j.recipe.steps.all():
                self.add_query(tmp.step_environment, collected)
            self.add_query(j.step_results, collected)

    def handle(self, *args, **options):
        num_events = options.get('num')
        events_count = models.Event.objects.count()
        if num_events > events_count:
            num_events = events_count

        events = models.Event.objects.select_related('base__branch__repository__user__server',
            'head__branch__repository__user__server',
            'pull_request',
            'build_user'
            ).prefetch_related("jobs").order_by('created').all()[(events_count-num_events):]
        output_filename = options.get('output')
        indent = options.get('indent')
        collected = []

        self.stdout.write("Dumping %s events" % events.count())
        for e in events:
            self.add_event(e, collected)
        # This could pull in a lot of additional events so disable it for now
        #for pr in models.PullRequest.objects.filter(closed=False).all():
        #  self.add_obj(pr, collected)
        #  self.add_obj(pr.repository.user.server, collected)
        #  self.add_obj(pr.repository.user, collected)
        #  self.add_obj(pr.repository, collected)
        #  for e in pr.events.all():
        #    self.add_event(e, collected)

        for branch in models.Branch.objects.exclude(status=models.JobStatus.NOT_STARTED).select_related("repository__user__server").all():
            self.add_obj(branch.repository.user.server, collected)
            self.add_obj(branch.repository.user, collected)
            self.add_obj(branch.repository, collected)
            self.add_obj(branch, collected)

        self.stdout.write("Dumping %s records to %s" % (len(collected), output_filename))
        with open(output_filename, "w") as f:
            output = serializers.serialize("json", collected, indent=indent)
            f.write(output)
