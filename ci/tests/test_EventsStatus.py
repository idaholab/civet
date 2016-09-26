# -*- coding: utf-8 -*-

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

import DBTester
import utils
import datetime
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
    pr = utils.create_pr(title="{a, b} & <c> …", repo=self.repo)
    for commit in ['1234', '2345', '3456']:
      e = utils.create_event(user=self.owner, commit1=commit, branch1=self.branch, branch2=self.branch)
      e.pull_request = pr
      e.save()
      utils.create_job(recipe=pre, event=e, user=self.build_user)
      utils.create_job(recipe=test, event=e, user=self.build_user)
      utils.create_job(recipe=test1, event=e, user=self.build_user)
      utils.create_job(recipe=merge, event=e, user=self.build_user)
    self.compare_counts(recipes=4, deps=4, current=4, jobs=12, active=12, num_pr_recipes=4, events=3, users=2, repos=1, branches=1, commits=3, prs=1)

  def test_get_default_events_query(self):
    self.create_events()

    q = EventsStatus.get_default_events_query()
    with self.assertNumQueries(1):
      self.assertEqual(q.count(), 3)

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

    with self.assertNumQueries(5):
      info = EventsStatus.all_events_info()
      self.assertEqual(len(info), 3)
      # pre, blank, test, test1, blank, merge
      self.assertEqual(len(info[0]["jobs"]), 6)

    # make sure limit works
    with self.assertNumQueries(5):
      info = EventsStatus.all_events_info(limit=1)
      self.assertEqual(len(info), 1)
      self.assertEqual(len(info[0]["jobs"]), 6)

    last_modified = models.Event.objects.last().last_modified
    last_modified = last_modified + datetime.timedelta(0,10)

    # make sure last_modified works
    with self.assertNumQueries(5):
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

  def test_events_info(self):
    self.create_events()

    ev = models.Event.objects.first()
    info = EventsStatus.events_info([ev])
    self.assertEqual(len(info), 1)

    ev = models.Event.objects.all()
    info = EventsStatus.events_info(ev)
    self.assertEqual(len(info), 3)
