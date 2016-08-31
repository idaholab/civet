
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
from ci import RepositoryStatus, models

class Tests(DBTester.DBTester):
  def create_repos(self, active=False):
    self.set_counts()
    owner = utils.create_user(name="idaholab")
    for repo_name in ['repo0', 'repo1', 'repo2']:
      repo = utils.create_repo(name=repo_name, user=owner)
      repo.active = active
      repo.save()
      for branch_name in ['test0', 'test1', 'test2']:
        utils.create_branch(name=branch_name, repo=repo)
      for num in [0, 1, 2]:
        utils.create_pr(title="pr%s" % num, number=num, repo=repo)
    active_repos = 0
    if active:
      active_repos = 3
    self.compare_counts(users=1, repos=3, branches=9, prs=9, active_repos=active_repos)

  def test_main_repos_status(self):
    self.create_repos()

    # None active
    with self.assertNumQueries(1):
      repos = RepositoryStatus.main_repos_status()
      self.assertEqual(len(repos), 0)

    for repo in models.Repository.objects.all():
      repo.active = True
      repo.save()

    # All repos active, no branches have their status set
    with self.assertNumQueries(3):
      repos = RepositoryStatus.main_repos_status()
      self.assertEqual(len(repos), 3)
      for repo in repos:
        self.assertEqual(len(repo["branches"]), 0)
        self.assertEqual(len(repo["prs"]), 3)

    for branch in models.Branch.objects.all():
      branch.status = models.JobStatus.SUCCESS
      branch.save()

    # All repos active, all branches active
    with self.assertNumQueries(3):
      repos = RepositoryStatus.main_repos_status()
      self.assertEqual(len(repos), 3)
      for repo in repos:
        self.assertEqual(len(repo["branches"]), 3)
        self.assertEqual(len(repo["prs"]), 3)

    last_modified = models.Repository.objects.first().last_modified + datetime.timedelta(0,10)
    # Nothing
    with self.assertNumQueries(3):
      repos = RepositoryStatus.main_repos_status(last_modified=last_modified)
      self.assertEqual(len(repos), 0)

    # Trye to close some PRs
    for pr in models.PullRequest.objects.all():
      pr.closed = True
      pr.save()
    # All repos active, all branches active, PRs closed
    with self.assertNumQueries(3):
      repos = RepositoryStatus.main_repos_status()
      self.assertEqual(len(repos), 3)
      for repo in repos:
        self.assertEqual(len(repo["branches"]), 3)
        self.assertEqual(len(repo["prs"]), 0)

  def test_filter_repos_status(self):
    self.create_repos(active=True)

    # All repos active, no branches have their status set
    pks = [models.Repository.objects.first().pk]
    with self.assertNumQueries(3):
      repos = RepositoryStatus.filter_repos_status(pks)
      self.assertEqual(len(repos), 1)
      for repo in repos:
        self.assertEqual(len(repo["branches"]), 0)
        self.assertEqual(len(repo["prs"]), 3)

  def test_get_repos_status(self):
    self.create_repos()

    # None active
    q = models.Repository.objects
    with self.assertNumQueries(3):
      repos = RepositoryStatus.get_repos_status(repo_q=q)
      self.assertEqual(len(repos), 3)

    q = models.Repository.objects.filter(active=True)
    with self.assertNumQueries(1):
      repos = RepositoryStatus.get_repos_status(repo_q=q)
      self.assertEqual(len(repos), 0)

    last_modified = models.Repository.objects.first().last_modified + datetime.timedelta(0,10)
    # None active
    q = models.Repository.objects
    with self.assertNumQueries(3):
      repos = RepositoryStatus.get_repos_status(repo_q=q, last_modified=last_modified)
      self.assertEqual(len(repos), 0)
