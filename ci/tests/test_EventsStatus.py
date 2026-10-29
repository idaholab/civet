# -*- coding: utf-8 -*-

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
from ci.tests import DBTester, utils
import datetime
from django.urls import reverse
from django.utils.html import escape, format_html
from ci import EventsStatus, models


class Tests(DBTester.DBTester):
    def create_events(self):
        self.set_counts()
        self.build_user = utils.create_user_with_token(name="moosebuild")
        self.owner = utils.create_user(name="idaholab")
        self.repo = utils.create_repo(name="civet", user=self.owner)
        self.branch = utils.create_branch(name="devel", repo=self.repo)
        pre = utils.create_recipe(name="Precheck", user=self.build_user, repo=self.repo)
        test = utils.create_recipe(name="Test", user=self.build_user, repo=self.repo)
        test1 = utils.create_recipe(name="Test1", user=self.build_user, repo=self.repo)
        test.depends_on.add(pre)
        test1.depends_on.add(pre)
        merge = utils.create_recipe(name="Merge", user=self.build_user, repo=self.repo)
        merge.depends_on.add(test)
        merge.depends_on.add(test1)
        pr = utils.create_pr(
            title="{a, b} & <c> … somereallylongwordthatshouldgettruncated",
            repo=self.repo,
        )
        pr.username = "pr_user"
        pr.save()
        for commit in ["1234", "2345", "3456"]:
            e = utils.create_event(
                user=self.owner,
                commit1=commit,
                branch1=self.branch,
                branch2=self.branch,
            )
            e.pull_request = pr
            e.description = "some description"
            e.save()
            j = utils.create_job(recipe=pre, event=e, user=self.build_user)
            j.seconds = datetime.timedelta(seconds=10)
            j.failed_step = "failed step"
            j.running_step = "3/5"
            j.save()
            utils.create_job(recipe=test, event=e, user=self.build_user)
            utils.create_job(recipe=test1, event=e, user=self.build_user)
            utils.create_job(recipe=merge, event=e, user=self.build_user)

        self.compare_counts(
            recipes=4,
            deps=4,
            current=4,
            jobs=12,
            active=12,
            num_pr_recipes=4,
            events=3,
            users=2,
            repos=1,
            branches=1,
            commits=3,
            prs=1,
        )

    def test_get_default_events_query(self):
        self.create_events()

        q = EventsStatus.get_default_events_query()
        with self.assertNumQueries(1):
            self.assertEqual(q.count(), 3)

        q = EventsStatus.get_default_events_query(filter_repo_ids=[self.repo.id])
        with self.assertNumQueries(1):
            self.assertEqual(q.count(), 3)

        q = EventsStatus.get_default_events_query(filter_repo_ids=[])
        with self.assertNumQueries(0):
            self.assertEqual(q.count(), 0)

        event_q = models.Event.objects.filter(head__sha="1234")
        q = EventsStatus.get_default_events_query(event_q=event_q)
        with self.assertNumQueries(1):
            self.assertEqual(q.count(), 1)

        event_q = models.Event.objects.filter(head__sha="invalid")
        q = EventsStatus.get_default_events_query(event_q=event_q)
        with self.assertNumQueries(1):
            self.assertEqual(q.count(), 0)

    def test_all_events_info(self):
        self.create_events()

        with self.assertNumQueries(4):
            info = EventsStatus.all_events_info()
            self.assertEqual(len(info), 3)
            # pre, blank, test, test1, blank, merge
            self.assertEqual(len(info[0]["jobs"]), 6)

        # make sure limit works
        with self.assertNumQueries(4):
            info = EventsStatus.all_events_info(limit=1)
            self.assertEqual(len(info), 1)
            self.assertEqual(len(info[0]["jobs"]), 6)

        last_modified = models.Event.objects.last().last_modified
        last_modified = last_modified + datetime.timedelta(0, 10)

        # make sure last_modified works
        with self.assertNumQueries(4):
            info = EventsStatus.all_events_info(last_modified=last_modified)
            self.assertEqual(len(info), 0)

    def test_events_with_head(self):
        self.create_events()

        q = EventsStatus.events_with_head()
        with self.assertNumQueries(1):
            self.assertEqual(q.count(), 3)

        event_q = models.Event.objects.filter(head__sha="1234")
        q = EventsStatus.events_with_head(event_q=event_q)
        q = EventsStatus.get_default_events_query(event_q=event_q)
        with self.assertNumQueries(1):
            self.assertEqual(q.count(), 1)

        event_q = models.Event.objects.filter(head__sha="invalid")
        q = EventsStatus.events_with_head(event_q=event_q)
        with self.assertNumQueries(1):
            self.assertEqual(q.count(), 0)

    def test_job_description_escaped(self):
        owner = utils.create_user(name="idaholab")
        build_user = utils.create_user_with_token(name="moosebuild")
        repo = utils.create_repo(name="civet", user=owner)
        branch = utils.create_branch(name="devel", repo=repo)
        recipe = utils.create_recipe(name="<r&\"x'>", user=build_user, repo=repo)
        ev = utils.create_event(user=owner, branch1=branch, branch2=branch)
        job = utils.create_job(recipe=recipe, event=ev, user=build_user)

        def description():
            q = EventsStatus.get_default_events_query()
            return EventsStatus.events_info(q)[0]["job_groups"][0][0]["description"]

        # No optional parts
        url = reverse("ci:view_job", args=[job.pk])
        expected = format_html('<a href="{}">{}</a>', url, job.unique_name())
        self.assertEqual(expected, '<a href="%s">%s</a>' % (url, escape(recipe.name)))
        self.assertNotIn("<r", expected)
        self.assertEqual(description(), expected)
        self.assertTrue(hasattr(description(), "__html__"))

        # Everything the description can contain, none of it trusted
        job.seconds = datetime.timedelta(seconds=10)
        job.failed_step = '<failed> & "step"'
        job.running_step = "'3/5' <b>"
        job.invalidated = True
        job.save()
        expected = (
            format_html('<a href="{}">{}</a>', url, job.unique_name())
            + format_html("<br />{}", "0:00:10")
            + format_html("<br />{}", job.failed_step)
            + format_html("<br />{}", job.running_step)
            + "<br />(Invalidated)"
        )
        self.assertNotIn("<failed>", expected)
        self.assertNotIn("<b>", expected)
        self.assertEqual(description(), expected)
        self.assertTrue(hasattr(description(), "__html__"))

    def test_events_info(self):
        self.create_events()

        ev = models.Event.objects.first()
        info = EventsStatus.events_info([ev])
        self.assertEqual(len(info), 1)

        ev = models.Event.objects.all()
        info = EventsStatus.events_info(ev)
        self.assertEqual(len(info), 3)

    def test_multi_line(self):
        self.create_events()
        e = utils.create_event(
            user=self.owner,
            commit1="456",
            branch1=self.branch,
            branch2=self.branch,
            cause=models.Event.PUSH,
        )
        e.description = "some description"
        e.save()
        event_q = EventsStatus.get_default_events_query()[:30]
        info = EventsStatus.multiline_events_info(event_q, max_jobs_per_line=100)
        self.assertEqual(len(info), 3)
        self.assertEqual(len(info[0]["jobs"]), 6)

        info = EventsStatus.multiline_events_info(event_q, max_jobs_per_line=1)
        self.assertEqual(len(info), 18)

    def test_get_single_event_for_open_prs(self):
        self.create_events()

        pr = models.PullRequest.objects.latest()
        latest_event = pr.events.latest()
        # 1. The latest event of each PullRequest
        # 2. Prefetch the jobs
        # 3. Prefetch the build configs of the recipes
        # 4. Prefetch the dependencies of the recipes
        # 5. jobs count below; the jobs are prefetched to prefetched_jobs
        with self.assertNumQueries(5):
            info = EventsStatus.get_single_event_for_open_prs([pr.pk])
            self.assertEqual(len(info), 1)  # should only have the latest event
            self.assertEqual(info[0].pk, latest_event.pk)
            # pre, test, test1, merge
            self.assertEqual(info[0].jobs.count(), 4)

        with self.assertNumQueries(0):
            info = EventsStatus.get_single_event_for_open_prs(
                [pr.pk], filter_repo_ids=[]
            )
            self.assertEqual(len(info), 0)

        with self.assertNumQueries(4):
            info = EventsStatus.get_single_event_for_open_prs(
                [pr.pk], filter_repo_ids=[self.repo.id]
            )
            self.assertEqual(len(info), 1)

        last_modified = latest_event.last_modified + datetime.timedelta(0, 10)

        # Nothing to prefetch
        with self.assertNumQueries(1):
            info = EventsStatus.get_single_event_for_open_prs([pr.pk], last_modified)
            self.assertEqual(len(info), 0)

        last_modified = latest_event.last_modified - datetime.timedelta(0, 10)
        with self.assertNumQueries(4):
            info = EventsStatus.get_single_event_for_open_prs([pr.pk], last_modified)
            self.assertEqual(len(info), 1)
            self.assertEqual(info[0].pk, latest_event.pk)
