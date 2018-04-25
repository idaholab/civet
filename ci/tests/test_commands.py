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
from django.core import management
from django.core.management.base import CommandError
from django.utils.six import StringIO
from django.test import override_settings
from mock import patch
from ci import models
from . import utils
import DBTester
import json
from requests_oauthlib import OAuth2Session

@override_settings(INSTALLED_GITSERVERS=[utils.github_config()])
class Tests(DBTester.DBTester):
    def setUp(self):
        super(Tests, self).setUp()
        self.create_default_recipes()

    def _split_output(self, out):
        tmp = out.getvalue().split("-"*50)
        tmp = [ t.strip() for t in tmp]
        print(tmp)
        return tmp

    @patch.object(OAuth2Session, 'get')
    def test_sync_open_prs(self, mock_get):
        r = models.Recipe.objects.first()
        repo = r.repository
        repo.active = True
        repo.save()

        pr = utils.create_pr(title="TESTPR")
        pr.closed = False
        pr.save()

        pr0 = {"number": pr.number, "title": "PR 1", "html_url": "first_url" }
        pr1 = {"number": pr.number + 1, "title": "PR 2", "html_url": "second_url" }
        mock_get.return_value = utils.Response([pr1])

        # A PR with recipe but its repository isn't active
        out = StringIO()
        management.call_command("sync_open_prs", stdout=out)
        self.assertEqual('', self._split_output(out)[0])

        pr.repository = repo
        pr.save()

        # A PR with a good repo, should be closed
        out = StringIO()
        management.call_command("sync_open_prs", stdout=out)
        self.assertIn(pr.title, out.getvalue())
        self.assertIn(str(pr.number), out.getvalue())
        self.assertIn(str(pr.repository), out.getvalue())
        pr.refresh_from_db()
        self.assertEqual(pr.closed, True)

        # Try to sync a specific repository that exists
        out = StringIO()
        pr.closed = False
        pr.save()
        management.call_command("sync_open_prs", "--dryrun", "--repo", str(repo), stdout=out)
        self.assertIn(pr.title, out.getvalue())
        self.assertIn(str(pr.number), out.getvalue())
        self.assertIn(str(pr.repository), out.getvalue())
        pr.refresh_from_db()
        self.assertEqual(pr.closed, False)

        # Try to sync a specific repository that exists
        out = StringIO()
        management.call_command("sync_open_prs", "--repo", str(repo), stdout=out)
        self.assertIn(pr.title, out.getvalue())
        self.assertIn(str(pr.number), out.getvalue())
        self.assertIn(str(pr.repository), out.getvalue())
        pr.refresh_from_db()
        self.assertEqual(pr.closed, True)

        # Make sure dry run doesn't change anything
        out = StringIO()
        pr.closed = False
        pr.save()
        management.call_command("sync_open_prs", "--dryrun", stdout=out)
        self.assertIn(pr.title, out.getvalue())
        self.assertIn(str(pr.number), out.getvalue())
        self.assertIn(str(pr.repository), out.getvalue())
        pr.refresh_from_db()
        self.assertEqual(pr.closed, False)

        mock_get.return_value = utils.Response([pr0, pr1])
        # Server has other PRs that CIVET doesn't have
        out = StringIO()
        management.call_command("sync_open_prs", "--dryrun", stdout=out)
        self.assertNotIn(pr.title, out.getvalue())
        self.assertNotIn("#%s" % pr.number, out.getvalue())
        self.assertIn("PRs open on server but not open on CIVET", out.getvalue())
        self.assertIn("PR 2", out.getvalue())
        self.assertIn("second_url", out.getvalue())
        self.assertIn("#%s" % (pr.number+1), out.getvalue())
        pr.refresh_from_db()
        self.assertEqual(pr.closed, False)

        # Try to sync a specific repository that doesn't exist
        out = StringIO()
        management.call_command("sync_open_prs", "--dryrun", "--repo", "foo/bar", stdout=out)
        self.assertEqual("", out.getvalue())

        # If the git server encounters an error then it shouldn't do anything
        mock_get.return_value = utils.Response(status_code=404)
        out = StringIO()
        management.call_command("sync_open_prs", stdout=out)
        self.assertIn("Error getting open PRs for %s" % repo, out.getvalue())
        pr.refresh_from_db()
        self.assertEqual(pr.closed, False)

    def test_dump_latest(self):
        out = StringIO()
        management.call_command("dump_latest", stdout=out)
        self.assertIn("Dumping 0 events", out.getvalue())

        ev = utils.create_event()
        management.call_command("dump_latest", stdout=out)
        self.assertIn("Dumping 1 events", out.getvalue())

        with open("out.json", "r") as f:
            data = f.read()
        out = json.loads(data)
        count = 0
        for entry in out:
            if entry["model"] == "ci.event":
                self.assertEqual(ev.pk, entry["pk"])
                count = 1
        self.assertEqual(count, 1)

    def test_disable_repo(self):
        out = StringIO()
        with self.assertRaises(CommandError):
            management.call_command("disable_repo", "--dry-run", stdout=out)
        with self.assertRaises(CommandError):
            management.call_command("disable_repo", "--dry-run", "--owner", "foo", stdout=out)

        repo = utils.create_repo()

        with self.assertRaises(CommandError):
            management.call_command("disable_repo", "--dry-run", "--owner", repo.user.name, "--repo", "<repo>", stdout=out)

        repo.active = True
        repo.save()
        branch = utils.create_branch(repo=repo)
        branch.status = models.JobStatus.SUCCESS
        branch.save()
        pr = utils.create_pr(repo=repo)
        pr.closed = False
        pr.save()

        management.call_command("disable_repo", "--dry-run", "--owner", repo.user.name, "--repo", repo.name, stdout=out)
        repo.refresh_from_db()
        self.assertIs(repo.active, True)
        branch.refresh_from_db()
        self.assertEqual(branch.status, models.JobStatus.SUCCESS)
        pr.refresh_from_db()
        self.assertIs(pr.closed, False)

        management.call_command("disable_repo", "--owner", repo.user.name, "--repo", repo.name, stdout=out)
        repo.refresh_from_db()
        self.assertIs(repo.active, False)
        branch.refresh_from_db()
        self.assertEqual(branch.status, models.JobStatus.NOT_STARTED)
        pr.refresh_from_db()
        self.assertIs(pr.closed, True)

    def test_load_recipes(self):
        with utils.RecipeDir():
            management.call_command("load_recipes", "--install-webhooks")

    @patch.object(OAuth2Session, 'get')
    def test_user_access(self, mock_get):
        out = StringIO()
        mock_get.return_value = utils.Response(status_code=404)
        with self.assertRaises(CommandError):
            management.call_command("user_access", stdout=out)
        with self.assertRaises(models.GitUser.DoesNotExist):
            management.call_command("user_access", "--master", "nobody", stdout=out)
        with self.assertRaises(CommandError):
            management.call_command("user_access", "--master", self.owner.name, stdout=out)

        out = StringIO()
        management.call_command("user_access", "--master", self.build_user.name, stdout=out)

        repo1 = {'name': 'repo1', 'owner': {'login': 'owner'} }
        repo2 = {'name': 'repo2', 'owner': {'login': 'owner'} }
        mock_get.side_effect = [utils.Response([repo1]), utils.Response([repo2])]

        out = StringIO()
        management.call_command("user_access", "--master", self.build_user.name, "--user", "owner", stdout=out)
