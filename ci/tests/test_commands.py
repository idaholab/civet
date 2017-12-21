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

from django.core import management
from django.utils.six import StringIO
from django.test import override_settings
from mock import patch
from ci import models
from . import utils
from ci.github import api
import DBTester

@override_settings(INSTALLED_GITSERVERS=[utils.github_config()])
class Tests(DBTester.DBTester):
    def setUp(self):
        super(Tests, self).setUp()
        self.create_default_recipes()

    @patch.object(api.GitHubAPI, 'get_open_prs')
    def test_sync_open_prs(self, mock_open_prs):
        mock_open_prs.return_value = []

        out = StringIO()
        management.call_command("sync_open_prs", stdout=out)
        self.assertEqual("", out.getvalue())

        r = models.Recipe.objects.first()
        repo = r.repository
        repo.active = True
        repo.save()

        pr = utils.create_pr(title="TESTPR")
        pr.closed = False
        pr.save()

        # A PR with recipe but its repository isn't active
        out = StringIO()
        management.call_command("sync_open_prs", stdout=out)
        self.assertEqual("", out.getvalue())

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

        git_response = [
                {"number": pr.number,
                    "title": "PR 1",
                    "html_url": "first_url",
                },
                {"number": pr.number + 1,
                    "title": "PR 2",
                    "html_url": "second_url",
                },
                ]
        mock_open_prs.return_value = git_response

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
        mock_open_prs.return_value = None
        out = StringIO()
        management.call_command("sync_open_prs", stdout=out)
        self.assertIn("Error getting open PRs for %s" % repo, out.getvalue())
        pr.refresh_from_db()
        self.assertEqual(pr.closed, False)
