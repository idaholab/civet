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
from django.urls import reverse
from django.test import override_settings
from mock import patch
from ci import models, views, Permissions, PullRequestEvent, GitCommitData
from ci.tests import utils, DBTester
from ci.github import api
import datetime


@override_settings(INSTALLED_GITSERVERS=[utils.github_config()])
class Tests(DBTester.DBTester):
    def setUp(self):
        super(Tests, self).setUp()
        self.create_default_recipes()

    def check_private_repo(self, url, type="get"):
        with patch.object(Permissions, "can_view_repo") as mock_can_view_repo:
            mock_can_view_repo.return_value = False
            if type == "get":
                response = self.client.get(url)
            elif type == "post":
                response = self.client.post(url)
            # Should look the same as an object that doesn't exist
            self.assertEqual(response.status_code, 404)

    def test_main(self):
        """
        testing ci:main
        """

        response = self.client.get(reverse("ci:main"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Sign in")
        self.assertNotContains(response, "Sign out")

        user = utils.get_test_user()
        utils.simulate_login(self.client.session, user)
        auth = user.auth()
        self.assertIn(auth._user_key, self.client.session)
        response = self.client.get(reverse("ci:main"))
        self.assertContains(response, "Sign out")
        self.assertNotContains(response, "Sign in")

    @patch.object(api.GitHubAPI, "has_write_access")
    @patch.object(api.GitHubAPI, "is_collaborator")
    @override_settings(PERMISSION_CACHE_TIMEOUT=0)
    def test_view_pr(self, mock_collab, mock_write):
        """
        testing ci:view_pr
        """
        # bad pr
        url = reverse(
            "ci:view_pr",
            args=[
                1000,
            ],
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)

        pr = utils.create_pr()
        ev = utils.create_event()
        ev.pull_request = pr
        ev.save()
        utils.create_job(event=ev)

        # needs to be active to view
        repo = pr.repository
        repo.active = True
        repo.save()

        user = utils.get_test_user()
        utils.simulate_login(self.client.session, user)

        # pr without events, as when purge_old_prs is deleting it
        empty_pr = utils.create_pr(number=2, repo=repo)
        response = self.client.get(reverse("ci:view_pr", args=[empty_pr.pk]))
        self.assertEqual(response.status_code, 404)
        self.assertTemplateUsed(response, "ci/404.html")
        empty_pr.delete()

        url = reverse(
            "ci:view_pr",
            args=[
                pr.pk,
            ],
        )
        r0 = utils.create_recipe(
            name="Recipe 0",
            repo=ev.base.branch.repository,
            cause=models.Recipe.CAUSE_PULL_REQUEST_ALT,
        )
        r1 = utils.create_recipe(
            name="Recipe 1",
            repo=ev.base.branch.repository,
            cause=models.Recipe.CAUSE_PULL_REQUEST_ALT,
        )
        # r0 also runs on a push, which gets noted on the form
        utils.create_recipe(
            name="Recipe 0",
            repo=ev.base.branch.repository,
            cause=models.Recipe.CAUSE_PUSH,
            branch=ev.base.branch,
        )
        push_note = "Default on a push to the %s branch" % ev.base.branch.name

        # user without write access, even a collaborator, can't see
        # or add any additional recipes
        mock_write.return_value = False
        for collab in [False, True]:
            mock_collab.return_value = collab
            self.set_counts()
            response = self.client.get(url)
            self.compare_counts()
            self.assertEqual(response.status_code, 200)
            self.assertFalse(response.context["allowed"])
            self.assertEqual(response.context["alt_choices"], [])
            self.assertEqual(response.context["default_choices"], [])
            self.assertNotContains(response, 'id="alt_pr"')
            self.assertNotContains(response, r0.display_name)
            self.assertNotContains(response, push_note)
            self.assertNotContains(response, "Additional Recipes")

            self.set_counts()
            response = self.client.post(url, {"recipes": [r0.pk, r1.pk]})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(pr.alternate_recipes.count(), 0)
            self.compare_counts()

        # user with write access, they get alternate recipe form
        mock_collab.return_value = False
        mock_write.return_value = True
        self.set_counts()
        response = self.client.get(url)
        self.compare_counts()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["allowed"])
        self.assertContains(response, "Additional Recipes")
        self.assertContains(response, 'id="alt_pr"')
        self.assertContains(response, r0.display_name)
        self.assertContains(response, push_note)

        self.set_counts()
        # post an invalid alternate recipe form
        response = self.client.post(url, {})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(pr.alternate_recipes.count(), 0)
        self.compare_counts()

        utils.simulate_login(self.client.session, user)
        # post a valid alternate recipe form
        self.set_counts()
        response = self.client.post(url, {"recipes": [r0.pk, r1.pk]})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(pr.alternate_recipes.count(), 2)
        # The original job plus the two alternate jobs are ready
        self.compare_counts(jobs=2, ready=3, active=2, num_pr_alts=2)
        # the updated form keeps the push note and shows the new selections
        self.assertContains(response, push_note)
        self.assertTrue(all(c["selected"] for c in response.context["alt_choices"]))

        # post again with the same recipes
        self.set_counts()
        response = self.client.post(url, {"recipes": [r0.pk, r1.pk]})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(pr.alternate_recipes.count(), 2)
        self.compare_counts()

        # post again different recipes. We don't auto cancel jobs.
        self.set_counts()
        response = self.client.post(url, {"recipes": [r0.pk]})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(pr.alternate_recipes.count(), 1)
        self.compare_counts(num_pr_alts=-1)

        # clear alt recipes
        self.set_counts()
        response = self.client.post(url, {"recipes": []})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(pr.alternate_recipes.count(), 0)
        self.compare_counts(num_pr_alts=-1)

        # private repo
        self.check_private_repo(url)

    def create_pr_data(self, pr_num=1, changed_files=[]):
        c1 = utils.create_commit(sha="1", branch=self.branch, user=self.owner)
        c2 = utils.create_commit(
            sha="%s" % pr_num * 120, branch=self.branch, user=self.owner
        )
        c1_data = GitCommitData.GitCommitData(
            self.owner.name, c1.repo().name, c1.branch.name, c1.sha, "", c1.server()
        )
        c2_data = GitCommitData.GitCommitData(
            self.owner.name, c2.repo().name, c2.branch.name, c2.sha, "", c2.server()
        )
        pr = PullRequestEvent.PullRequestEvent()
        pr.pr_number = pr_num
        pr.action = PullRequestEvent.PullRequestEvent.OPENED
        pr.build_user = self.build_user
        pr.title = "PR %s" % pr_num
        pr.html_url = "url"
        pr.full_text = ""
        pr.base_commit = c1_data
        pr.head_commit = c2_data
        pr.changed_files = changed_files
        self.set_counts()
        pr.save()

    @patch.object(api.GitHubAPI, "has_write_access")
    @patch.object(api.GitHubAPI, "is_collaborator")
    def test_view_pr_matched(self, mock_collab, mock_write):
        user = utils.get_test_user()
        utils.simulate_login(self.client.session, user)
        mock_collab.return_value = True
        mock_write.return_value = True
        with self.settings(
            INSTALLED_GITSERVERS=[
                utils.github_config(recipe_label_activation=utils.default_labels())
            ]
        ):
            self.set_label_on_recipes()
            changed_files = ["docs/foo", "docs/bar"]
            self.set_counts()
            self.create_pr_data(pr_num=2, changed_files=changed_files)
            self.compare_counts(
                jobs=2,
                active=2,
                events=1,
                ready=1,
                prs=1,
                num_pr_alts=1,
                active_repos=1,
            )
            pr = models.PullRequest.objects.get(number=2)
            self.assertEqual(pr.alternate_recipes.count(), 1)
            url = reverse(
                "ci:view_pr",
                args=[
                    pr.pk,
                ],
            )

            # try adding a default recipe
            recipes = models.Recipe.objects.order_by("created").filter(
                cause=models.Recipe.CAUSE_PULL_REQUEST
            )
            self.assertEqual(recipes.count(), 2)
            self.set_counts()
            data = {
                "recipes": [pr.alternate_recipes.first().pk],
                "default_recipes": [
                    recipes[1].pk,
                ],
            }
            response = self.client.post(url, data)
            self.assertEqual(response.status_code, 200)
            self.compare_counts(jobs=1, active=1)

            # shouldn't be able to remove one of the default
            self.set_counts()
            data["default_recipes"] = []
            response = self.client.post(url, data)
            self.assertEqual(response.status_code, 200)
            self.compare_counts()

            # try the original again, should give a form error (which we can't detect)
            data["default_recipes"] = [
                recipes[1].pk,
            ]
            self.set_counts()
            response = self.client.post(url, data)
            self.assertEqual(response.status_code, 200)
            self.compare_counts()

    @patch.object(api.GitHubAPI, "is_collaborator")
    @override_settings(PERMISSION_CACHE_TIMEOUT=0)
    def test_view_event(self, mock_collab):
        """
        testing ci:view_event
        """
        mock_collab.return_value = False

        # invalid event
        response = self.client.get(
            reverse(
                "ci:view_event",
                args=[
                    1000,
                ],
            )
        )
        self.assertEqual(response.status_code, 404)

        ev = utils.create_event()
        repo = ev.base.branch.repository
        repo.active = True
        repo.save()

        url = reverse("ci:view_event", args=[ev.pk])
        # valid event
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

        # valid event while signed in
        user = utils.get_test_user()
        utils.simulate_login(self.client.session, user)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

        # private repo
        self.check_private_repo(url)

    @patch.object(Permissions, "can_invalidate")
    @patch.object(Permissions, "can_cancel")
    @patch.object(Permissions, "has_write_access")
    def test_view_event_permissions(self, mock_write, mock_cancel, mock_invalidate):
        job = utils.create_job()
        job.active = False
        job.save()
        repo = job.recipe.repository
        repo.active = True
        repo.save()
        url = reverse("ci:view_event", args=[job.event.pk])

        # activation requires write access
        mock_write.return_value = True
        mock_cancel.return_value = False
        mock_invalidate.return_value = False
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="activate_form"')
        self.assertNotContains(response, 'id="cancel_form"')
        self.assertNotContains(response, 'id="invalidate_form"')

        mock_write.return_value = False
        mock_cancel.return_value = True
        mock_invalidate.return_value = True
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'id="activate_form"')
        self.assertContains(response, 'id="cancel_form"')
        self.assertContains(response, 'id="invalidate_form"')

    @override_settings(PERMISSION_CACHE_TIMEOUT=0)
    def test_view_job(self):
        """
        testing ci:view_job
        """
        response = self.client.get(
            reverse(
                "ci:view_job",
                args=[
                    1000,
                ],
            )
        )
        self.assertEqual(response.status_code, 404)

        job = utils.create_job()
        job.recipe.repository.active = True
        job.recipe.repository.save()

        url = reverse("ci:view_job", args=[job.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

        self.check_private_repo(url)

    def test_get_paginated(self):
        recipes = models.Recipe.objects.all().order_by("-id")
        self.assertEqual(models.Recipe.objects.count(), 6)
        # there are 6 recipes, so only 1 page
        # objs.number is the current page number
        request = self.factory.get("/foo?page=1")
        objs = views.get_paginated(request, recipes)
        self.assertEqual(objs.number, 1)
        self.assertEqual(objs.paginator.num_pages, 1)
        self.assertEqual(objs.paginator.count, 6)

        # Invalid page, so just returns the end page
        request = self.factory.get("/foo?page=2")
        objs = views.get_paginated(request, recipes)
        self.assertEqual(objs.number, 1)
        self.assertEqual(objs.paginator.num_pages, 1)
        self.assertEqual(objs.paginator.count, 6)

        for i in range(10):
            utils.create_recipe(name="recipe %s" % i)

        # now there are 16 recipes, so page=2 should be
        # valid
        request = self.factory.get("/foo?page=2")
        objs = views.get_paginated(request, recipes, 2)
        self.assertEqual(objs.number, 2)
        self.assertEqual(objs.paginator.num_pages, 8)
        self.assertEqual(objs.paginator.count, 16)

        # page=20 doesn't exist so it should return
        # the last page
        request = self.factory.get("/foo?page=20")
        objs = views.get_paginated(request, recipes, 2)
        self.assertEqual(objs.number, 8)
        self.assertEqual(objs.paginator.num_pages, 8)
        self.assertEqual(objs.paginator.count, 16)

        # Completely invalid page number so returns
        # the first page
        request = self.factory.get("/foo?page=foo")
        objs = views.get_paginated(request, recipes, 2)
        self.assertEqual(objs.number, 1)
        self.assertEqual(objs.paginator.num_pages, 8)
        self.assertEqual(objs.paginator.count, 16)

        # limit overrides the number of objects per page
        request = self.factory.get("/foo?limit=4")
        objs = views.get_paginated(request, recipes, 2)
        self.assertEqual(objs.number, 1)
        self.assertEqual(objs.paginator.num_pages, 4)

        # but is capped at 500
        request = self.factory.get("/foo?limit=1000")
        objs = views.get_paginated(request, recipes, 2)
        self.assertEqual(objs.paginator.per_page, 500)

    @override_settings(PERMISSION_CACHE_TIMEOUT=0)
    def test_view_repo(self):
        # invalid repo
        response = self.client.get(
            reverse(
                "ci:view_repo",
                args=[
                    1000,
                ],
            )
        )
        self.assertEqual(response.status_code, 404)

        repo = utils.create_repo()
        branch = utils.create_branch(repo=repo)
        branch.status = models.JobStatus.FAILED
        branch.save()
        utils.create_event(user=repo.user, branch1=branch, branch2=branch)
        repo.active = True
        repo.save()

        url = reverse("ci:view_repo", args=[repo.pk])

        # valid repo with branches
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

        # private repo
        self.check_private_repo(url)

    @override_settings(PERMISSION_CACHE_TIMEOUT=0)
    def test_view_owner_repo(self):
        # invalid repo
        response = self.client.get(reverse("ci:view_owner_repo", args=["foo", "bar"]))
        self.assertEqual(response.status_code, 404)

        repo = utils.create_repo()
        branch = utils.create_branch(repo=repo)
        branch.status = models.JobStatus.FAILED
        branch.save()
        utils.create_event(user=repo.user, branch1=branch, branch2=branch)
        repo.active = True
        repo.save()

        url = reverse("ci:view_owner_repo", args=[repo.user.name, repo.name])

        # valid repo with branches
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

        # private repo
        self.check_private_repo(url)

    @override_settings(PERMISSION_CACHE_TIMEOUT=0)
    def test_view_client(self):
        user = utils.get_test_user()
        with self.settings(
            INSTALLED_GITSERVERS=[utils.github_config(authorized_users=[])]
        ):
            url = reverse(
                "ci:view_client",
                args=[
                    1000,
                ],
            )
            response = self.client.get(url)
            self.assertEqual(response.status_code, 404)
            client = utils.create_client()

            # not logged in
            url = reverse(
                "ci:view_client",
                args=[
                    client.pk,
                ],
            )
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, "You are not allowed")

            # logged in but not on the authorized list
            utils.simulate_login(self.client.session, user)
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, "You are not allowed")

        with self.settings(
            INSTALLED_GITSERVERS=[utils.github_config(authorized_users=[user.name])]
        ):
            # logged in and on the authorized list
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
            self.assertNotContains(response, "You are not allowed")

            # Should be cached
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
            self.assertNotContains(response, "You are not allowed")

    @override_settings(PERMISSION_CACHE_TIMEOUT=0)
    def test_view_branch(self):
        response = self.client.get(
            reverse(
                "ci:view_branch",
                args=[
                    1000,
                ],
            )
        )
        self.assertEqual(response.status_code, 404)

        obj = utils.create_branch()
        obj.repository.active = True
        obj.repository.save()

        url = reverse("ci:view_branch", args=[obj.pk])

        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

        args = {"do_filter": 1, "filter_events": [models.Event.PULL_REQUEST]}
        response = self.client.get(url, args)
        self.assertEqual(response.status_code, 200)

        # POST not allowed
        response = self.client.post(url, args)
        self.assertEqual(response.status_code, 405)

        self.check_private_repo(url)

    @override_settings(PERMISSION_CACHE_TIMEOUT=0)
    def test_view_repo_branch(self):
        # invalid branch
        response = self.client.get(
            reverse("ci:view_repo_branch", args=["owner", "repo", "branch"])
        )
        self.assertEqual(response.status_code, 404)

        b = utils.create_branch()
        b.repository.active = True
        b.repository.save()

        url = reverse(
            "ci:view_repo_branch",
            args=[b.repository.user.name, b.repository.name, b.name],
        )

        # Valid
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

        # Private repo
        self.check_private_repo(url)

    def test_pr_list(self):
        response = self.client.get(reverse("ci:pullrequest_list"))
        self.assertEqual(response.status_code, 200)

    def test_branch_list(self):
        response = self.client.get(reverse("ci:branch_list"))
        self.assertEqual(response.status_code, 200)

    @patch.object(Permissions, "is_allowed_to_see_clients")
    @override_settings(PERMISSION_CACHE_TIMEOUT=0)
    def test_client_list(self, mock_allowed):
        mock_allowed.return_value = False
        for i in range(10):
            c = utils.create_client(name="client%s" % i)
            c.status = models.Client.RUNNING
            c.save()
        # not allowed
        response = self.client.get(reverse("ci:client_list"))
        self.assertEqual(response.status_code, 200)
        for c in models.Client.objects.all():
            self.assertNotContains(response, c.name)

        # allowed
        mock_allowed.return_value = True
        response = self.client.get(reverse("ci:client_list"))
        self.assertEqual(response.status_code, 200)
        for i in range(10):
            name = "client%s" % i
            self.assertContains(response, name)
            self.assertContains(response, 'status_%i" class="client_Running"' % (i + 1))

        inactive = []
        for i in range(5):
            c = models.Client.objects.get(name="client%s" % i)
            # we need to do it like this because a save() will automatically update it to current time
            models.Client.objects.filter(pk=c.pk).update(
                last_seen=c.last_seen - datetime.timedelta(seconds=160)
            )
            inactive.append(c.name)

        response = self.client.get(reverse("ci:client_list"))
        self.assertEqual(response.status_code, 200)
        for i in range(10):
            name = "client%s" % i
            self.assertContains(response, name)
            if name in inactive:
                self.assertContains(
                    response, 'status_%i" class="client_NotSeen"' % (i + 1)
                )
            else:
                self.assertContains(
                    response, 'status_%i" class="client_Running"' % (i + 1)
                )

        for name in inactive:
            c = models.Client.objects.get(name=name)
            models.Client.objects.filter(pk=c.pk).update(
                last_seen=c.last_seen - datetime.timedelta(seconds=2 * 7 * 24 * 60 * 60)
            )

        response = self.client.get(reverse("ci:client_list"))
        self.assertEqual(response.status_code, 200)
        for c in models.Client.objects.all():
            if c.name in inactive:
                self.assertNotContains(response, c.name)
                self.assertEqual(c.status, models.Client.DOWN)
            else:
                self.assertContains(response, c.name)

    def test_event_list(self):
        response = self.client.get(reverse("ci:event_list"))
        self.assertEqual(response.status_code, 200)

    @override_settings(PERMISSION_CACHE_TIMEOUT=0)
    def test_sha_events(self):
        e = utils.create_event()
        repo = e.head.branch.repository
        repo.active = True
        repo.save()

        url = reverse("ci:sha_events", args=["no_exist", repo.name, e.head.sha])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)

        # an event with the same head but a base repo that can't be
        # viewed (not active)
        hidden_repo = utils.create_repo(name="hidden_repo", user=repo.user)
        hidden_branch = utils.create_branch(name="hidden_branch", repo=hidden_repo)
        hidden_ev = utils.create_event(
            user=e.build_user,
            commit1=e.head.sha,
            branch1=e.head.branch,
            commit2="9999",
            branch2=hidden_branch,
        )
        self.assertEqual(hidden_ev.head, e.head)

        url = reverse("ci:sha_events", args=[repo.user.name, repo.name, e.head.sha])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual([ev.pk for ev in response.context["pages"]], [e.pk])

        self.check_private_repo(url)

    @patch.object(Permissions, "is_allowed_to_see_clients")
    def test_cronjobs(self, mock_allowed):
        mock_allowed.return_value = True
        utils.create_recipe(scheduler="* * * * *", branch=self.branch)
        response = self.client.get(reverse("ci:cronjobs"))
        self.assertEqual(response.status_code, 200)

        mock_allowed.return_value = False
        response = self.client.get(reverse("ci:cronjobs"))
        self.assertEqual(response.status_code, 200)

    @patch.object(Permissions, "is_allowed_to_see_clients")
    @override_settings(PERMISSION_CACHE_TIMEOUT=0)
    def test_recipe_crons(self, mock_allowed):
        mock_allowed.return_value = True
        r = utils.create_recipe(scheduler="* * * * *")
        r.repository.active = True
        r.repository.save()

        url = reverse("ci:recipe_crons", args=[r.pk])

        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

        # average time is computed from the successful jobs
        job = utils.create_job(recipe=r)
        job.status = models.JobStatus.SUCCESS
        job.seconds = datetime.timedelta(seconds=10)
        job.save()
        job = utils.create_job(recipe=r, event=utils.create_event(commit1="3456"))
        job.status = models.JobStatus.FAILED
        job.seconds = datetime.timedelta(seconds=20)
        job.save()
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.context["average_time"], datetime.timedelta(seconds=10)
        )
        visible_events = [ev.pk for ev in response.context["pages"]]
        self.assertEqual(len(visible_events), 2)

        # A recipe with the same filename in a repo the user can't see
        # shouldn't contribute events or to the average time
        other_repo = utils.create_repo(
            name="otherRepo", user=r.repository.user, active=False
        )
        other_recipe = utils.create_recipe(repo=other_repo, scheduler="* * * * *")
        self.assertEqual(other_recipe.filename, r.filename)
        other_branch = utils.create_branch(name="otherBranch", repo=other_repo)
        other_event = utils.create_event(commit1="5678", branch2=other_branch)
        job = utils.create_job(recipe=other_recipe, event=other_event)
        job.status = models.JobStatus.SUCCESS
        job.seconds = datetime.timedelta(seconds=30)
        job.save()
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual([ev.pk for ev in response.context["pages"]], visible_events)
        self.assertEqual(
            response.context["average_time"], datetime.timedelta(seconds=10)
        )

        self.check_private_repo(url)

    @patch.object(Permissions, "is_allowed_to_see_clients")
    def test_manual_cron(self, mock_allowed):
        mock_allowed.return_value = True
        r = utils.create_recipe(branch=self.branch)
        url = reverse("ci:manual_cron", args=[r.pk])

        # needs to be active to view
        repo = r.repository
        repo.active = True
        repo.save()

        # only post is allowed
        with patch.object(api.GitHubAPI, "last_sha") as mock_last_sha:
            mock_last_sha.return_value = "1234"
            self.set_counts()
            response = self.client.get(url)
            self.assertEqual(response.status_code, 405)
            self.compare_counts()

        response = self.client.post(url)
        self.assertEqual(response.status_code, 302)

        # with a latest SHA an event gets created
        with patch.object(api.GitHubAPI, "last_sha") as mock_last_sha:
            mock_last_sha.return_value = "1234"
            self.set_counts()
            response = self.client.post(url)
            self.assertEqual(response.status_code, 302)
            self.compare_counts(
                events=1,
                jobs=1,
                ready=1,
                commits=1,
                active=1,
                active_repos=1,
            )
            r.refresh_from_db()
            self.assertIsNotNone(r.last_scheduled)

        # private repo
        with patch.object(api.GitHubAPI, "last_sha") as mock_last_sha:
            mock_last_sha.return_value = "5678"
            self.set_counts()
            self.check_private_repo(url, type="post")
            self.compare_counts()

        mock_allowed.return_value = False
        response = self.client.post(url)
        self.assertEqual(response.status_code, 403)

    @patch.object(Permissions, "can_invalidate")
    @override_settings(PERMISSION_CACHE_TIMEOUT=0)
    def test_invalidate_event(self, mock_collab):
        # only post is allowed
        url = reverse("ci:invalidate_event", args=[1000])
        self.set_counts()
        response = self.client.get(url)
        self.assertEqual(response.status_code, 405)  # not allowed
        self.compare_counts()

        # invalid event
        self.set_counts()
        response = self.client.post(url)
        self.assertEqual(response.status_code, 404)  # not found
        self.compare_counts()

        j0, j1, j2, j3 = utils.create_test_jobs()

        # needs to be active to view
        repo = j0.recipe.repository
        repo.active = True
        repo.save()

        # can't invalidate
        mock_collab.return_value = False
        url = reverse("ci:invalidate_event", args=[j0.event.pk])
        self.set_counts()
        response = self.client.post(url)
        self.assertEqual(response.status_code, 302)  # redirect with error message
        self.compare_counts()

        client = utils.create_client()
        for j in [j0, j1, j2, j3]:
            j.client = client
            j.ready = True
            j.complete = True
            j.status = models.JobStatus.SUCCESS
            j.event.complete = False
            j.save()

        post_data = {"same_client": ""}

        # private repo
        self.set_counts()
        self.check_private_repo(url, type="post")
        self.compare_counts()

        # valid
        mock_collab.return_value = True
        self.set_counts()
        response = self.client.post(url, data=post_data)
        self.assertEqual(response.status_code, 302)  # redirect
        self.compare_counts(
            ready=-3, num_jobs_completed=-4, invalidated=4, num_changelog=4
        )
        redir_url = reverse("ci:view_event", args=[j0.event.pk])
        for j in [j0, j1, j2, j3]:
            j.refresh_from_db()
            self.assertRedirects(response, redir_url)
            self.assertEqual(j.step_results.count(), 0)
            self.assertFalse(j.complete)
            self.assertTrue(j.active)
            self.assertTrue(j.invalidated)
            self.assertFalse(j.same_client)
            self.assertEqual(j.client, None)
            self.assertEqual(j.seconds.seconds, 0)
            self.assertEqual(j.status, models.JobStatus.NOT_STARTED)
            self.assertFalse(j.event.complete)
            self.assertEqual(j.event.status, models.JobStatus.NOT_STARTED)
        self.assertTrue(j0.ready)
        self.assertFalse(j1.ready)
        self.assertFalse(j2.ready)
        self.assertFalse(j3.ready)

        # valid
        for j in [j0, j1, j2, j3]:
            j.client = client
            j.ready = True
            j.complete = True
            j.status = models.JobStatus.SUCCESS
            j.event.complete = False
            j.save()
            utils.create_step_result(job=j)
        post_data = {"same_client": "on"}
        self.set_counts()
        response = self.client.post(url, data=post_data)
        self.assertEqual(response.status_code, 302)  # redirect
        self.compare_counts(num_changelog=4, ready=-3, num_jobs_completed=-4)
        for j in [j0, j1, j2, j3]:
            j.refresh_from_db()
            self.assertRedirects(response, redir_url)
            self.assertEqual(j.step_results.count(), 0)
            self.assertFalse(j.complete)
            self.assertTrue(j.active)
            self.assertTrue(j.invalidated)
            self.assertTrue(j.same_client)
            self.assertEqual(j.client, client)
            self.assertEqual(j.seconds.seconds, 0)
            self.assertEqual(j.status, models.JobStatus.NOT_STARTED)
            self.assertFalse(j.event.complete)
            self.assertEqual(j.event.status, models.JobStatus.NOT_STARTED)

        self.assertTrue(j0.ready)
        self.assertFalse(j1.ready)
        self.assertFalse(j2.ready)
        self.assertFalse(j3.ready)

        post_data["comment"] = "some comment"
        post_data["post_to_pr"] = "on"
        self.set_counts()
        response = self.client.post(url, data=post_data)
        self.assertEqual(response.status_code, 302)  # redirect
        self.compare_counts(num_changelog=4)

        # Make sure when the first job completes the other
        # jobs will become ready
        j0.complete = True
        j0.status = models.JobStatus.SUCCESS
        j0.save()
        self.set_counts()
        j0.event.make_jobs_ready()
        self.compare_counts(ready=2)
        self.assertFalse(j0.event.check_done())

    @patch.object(Permissions, "is_server_admin")
    @override_settings(PERMISSION_CACHE_TIMEOUT=0)
    def test_prioritize_event(self, mock_perms):
        # only post is allowed
        url = reverse("ci:prioritize_event", args=[1000])
        self.set_counts()
        response = self.client.get(url)
        self.assertEqual(response.status_code, 405)  # not allowed
        self.compare_counts()

        # invalid event
        self.set_counts()
        response = self.client.post(url)
        self.assertEqual(response.status_code, 404)  # not found
        self.compare_counts()

        j0, j1, j2, j3 = utils.create_test_jobs()

        # needs to be active to view
        repo = j0.recipe.repository
        repo.active = True
        repo.save()

        # can't prioritize
        mock_perms.return_value = False
        url = reverse("ci:prioritize_event", args=[j0.event.pk])
        self.set_counts()
        response = self.client.post(url)
        self.assertEqual(response.status_code, 302)  # redirect with error message
        self.compare_counts()

        client = utils.create_client()
        for j in [j0, j1, j2, j3]:
            j.client = client
            j.ready = True
            j.complete = True
            j.status = models.JobStatus.SUCCESS
            j.event.complete = False
            j.save()
            self.assertIsNone(j.prioritized)

        post_data = {"comment": "foo"}

        # private repo
        self.set_counts()
        self.check_private_repo(url, type="post")
        self.compare_counts()

        # valid
        mock_perms.return_value = True
        self.set_counts()
        response = self.client.post(url, data=post_data)
        self.assertEqual(response.status_code, 302)  # redirect
        redir_url = reverse("ci:view_event", args=[j0.event.pk])
        self.assertRedirects(response, redir_url)
        self.compare_counts(num_changelog=4)
        for j in [j0, j1, j2, j3]:
            j.refresh_from_db()
            self.assertIsNotNone(j.prioritized)

    @patch.object(Permissions, "is_allowed_to_see_clients")
    @override_settings(PERMISSION_CACHE_TIMEOUT=0)
    def test_ready_jobs(self, mock_perms):
        # not allowed
        mock_perms.return_value = False
        response = self.client.get(reverse("ci:ready_jobs"))
        self.assertEqual(response.status_code, 200)
        self.assertIn(
            "You are not allowed to view the ready jobs",
            response.content.decode("utf-8"),
        )

        # no ready jobs
        mock_perms.return_value = True
        response = self.client.get(reverse("ci:ready_jobs"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("No ready jobs", response.content.decode("utf-8"))

        j0, j1, j2, j3 = utils.create_test_jobs()
        client = utils.create_client()
        for j in [j0, j1, j2, j3]:
            j.client = client
            j.ready = True
            j.event.complete = False
            j.save()

        repo = j0.recipe.repository
        repo.active = True
        repo.save()

        mock_perms.return_value = True
        response = self.client.get(reverse("ci:ready_jobs"))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf-8")
        self.assertIn("4 ready jobs", content)
        for j in [j0, j1, j2, j3]:
            self.assertIn(j.recipe.repository.name, content)
            self.assertIn(j.event.description, content)
            self.assertIn(j.recipe.display_name, content)

    @patch.object(Permissions, "can_cancel")
    @override_settings(PERMISSION_CACHE_TIMEOUT=0)
    def test_cancel_event(self, mock_collab):
        # only post is allowed
        url = reverse("ci:cancel_event", args=[1000])
        self.set_counts()
        response = self.client.get(url)
        self.assertEqual(response.status_code, 405)  # not allowed
        self.compare_counts()

        # invalid event
        self.set_counts()
        response = self.client.post(url)
        self.assertEqual(response.status_code, 404)  # not found
        self.compare_counts()

        step_result = utils.create_step_result()
        job = step_result.job
        job.event.pull_request = utils.create_pr()
        job.event.comments_url = "some url"
        job.event.save()

        # needs to be active to view
        repo = job.recipe.repository
        repo.active = True
        repo.save()

        # can't cancel
        mock_collab.return_value = False
        url = reverse("ci:cancel_event", args=[job.event.pk])
        self.set_counts()
        response = self.client.post(url)
        self.assertEqual(response.status_code, 302)  # redirect with error message
        self.compare_counts()

        # private
        self.set_counts()
        self.check_private_repo(url, type="post")
        self.compare_counts()

        # valid
        mock_collab.return_value = True
        post_data = {"post_to_pr": "on", "comment": "some comment"}
        self.set_counts()
        response = self.client.post(url, post_data)
        self.compare_counts(
            canceled=1,
            events_canceled=1,
            num_events_completed=1,
            num_jobs_completed=1,
            num_changelog=1,
        )
        self.assertEqual(response.status_code, 302)  # redirect
        ev_url = reverse("ci:view_event", args=[job.event.pk])
        self.assertRedirects(response, ev_url)
        job = models.Job.objects.get(pk=job.pk)
        self.assertEqual(job.status, models.JobStatus.CANCELED)
        self.assertEqual(job.event.status, models.JobStatus.CANCELED)

    @patch.object(Permissions, "can_cancel")
    @override_settings(PERMISSION_CACHE_TIMEOUT=0)
    def test_cancel_job(self, mock_collab):
        # only post is allowed
        url = reverse("ci:cancel_job", args=[1000])
        self.set_counts()
        response = self.client.get(url)
        self.assertEqual(response.status_code, 405)  # not allowed
        self.compare_counts()

        # invalid job
        self.set_counts()
        response = self.client.post(url)
        self.assertEqual(response.status_code, 404)  # not found
        self.compare_counts()

        step_result = utils.create_step_result()
        job = step_result.job

        # needs to be active to view
        repo = job.recipe.repository
        repo.active = True
        repo.save()

        # can't cancel
        mock_collab.return_value = False
        self.set_counts()
        url = reverse("ci:cancel_job", args=[job.pk])
        response = self.client.post(url)
        self.assertEqual(response.status_code, 403)  # forbidden
        self.compare_counts()

        # private repo
        self.set_counts()
        self.check_private_repo(url, type="post")
        self.compare_counts()

        # valid
        mock_collab.return_value = True
        post_data = {"post_to_pr": "on", "comment": "some comment"}
        self.set_counts()
        response = self.client.post(url, post_data)
        self.assertEqual(response.status_code, 302)  # redirect
        self.compare_counts(
            canceled=1,
            events_canceled=1,
            num_events_completed=1,
            num_jobs_completed=1,
            num_changelog=1,
            active_branches=1,
        )
        job = models.Job.objects.get(pk=job.pk)
        job_url = reverse("ci:view_job", args=[job.pk])
        self.assertRedirects(response, job_url)
        self.assertEqual(job.status, models.JobStatus.CANCELED)
        self.assertEqual(job.event.base.branch.status, models.JobStatus.CANCELED)

    def check_job_invalidated(self, job, same_client=False, client=None):
        job.refresh_from_db()
        self.assertEqual(job.step_results.count(), 0)
        self.assertFalse(job.complete)
        self.assertTrue(job.active)
        self.assertTrue(job.invalidated)
        self.assertEqual(job.same_client, same_client)
        self.assertEqual(job.seconds.seconds, 0)
        self.assertEqual(job.client, client)
        self.assertEqual(job.status, models.JobStatus.NOT_STARTED)

    @patch.object(Permissions, "can_invalidate")
    def test_invalidate_client(self, mock_collab):
        job = utils.create_job()

        # needs to be active to view
        repo = job.recipe.repository
        repo.active = True
        repo.save()

        client = utils.create_client()
        client2 = utils.create_client(name="client2")
        mock_collab.return_value = True
        url = reverse("ci:invalidate", args=[job.pk])
        post_data = {}
        self.set_counts()
        response = self.client.post(url, data=post_data)
        self.assertEqual(response.status_code, 302)  # redirect
        self.compare_counts(ready=1, invalidated=1, num_changelog=1)
        self.check_job_invalidated(job)
        job.client = client
        job.save()

        self.set_counts()
        post_data["client_list"] = client.pk
        response = self.client.post(url, data=post_data)
        self.assertEqual(response.status_code, 302)  # redirect
        self.compare_counts(num_changelog=1)
        self.check_job_invalidated(job, True, client)

        self.set_counts()
        post_data["client_list"] = client2.pk
        response = self.client.post(url, data=post_data)
        self.assertEqual(response.status_code, 302)  # redirect
        self.compare_counts(num_changelog=1)
        self.check_job_invalidated(job, True, client2)

        self.set_counts()
        post_data["client_list"] = 0
        response = self.client.post(url, data=post_data)
        self.assertEqual(response.status_code, 302)  # redirect
        self.compare_counts(num_changelog=1)
        self.check_job_invalidated(job, False)

    @patch.object(Permissions, "can_invalidate")
    def test_invalidate(self, mock_collab):
        # only post is allowed
        url = reverse("ci:invalidate", args=[1000])
        self.set_counts()
        response = self.client.get(url)
        self.assertEqual(response.status_code, 405)  # not allowed
        self.compare_counts()

        # invalid job
        self.set_counts()
        response = self.client.post(url)
        self.assertEqual(response.status_code, 404)  # not found
        self.compare_counts()

        step_result = utils.create_step_result()
        job = step_result.job
        job.event.pull_request = utils.create_pr()
        job.event.comments_url = "some url"
        job.event.save()
        repo = job.recipe.repository
        repo.active = True
        repo.save()

        # can't invalidate
        mock_collab.return_value = False
        url = reverse("ci:invalidate", args=[job.pk])
        self.set_counts()
        response = self.client.post(url)
        self.assertEqual(response.status_code, 403)  # forbidden
        self.compare_counts()

        # valid
        client = utils.create_client()
        job.client = client
        job.save()
        post_data = {
            "post_to_pr": "on",
            "comment": "some comment",
            "same_client": "",
        }

        # private repo
        self.set_counts()
        self.check_private_repo(url, type="post")
        self.compare_counts()

        mock_collab.return_value = True
        self.set_counts()
        response = self.client.post(url, data=post_data)
        self.assertEqual(response.status_code, 302)  # redirect
        self.compare_counts(ready=1, invalidated=1, num_changelog=1)
        job.refresh_from_db()
        redir_url = reverse("ci:view_job", args=[job.pk])
        self.assertRedirects(response, redir_url)
        self.check_job_invalidated(job)

        post_data["same_client"] = "on"
        utils.create_step_result(job=job)
        job.client = client
        job.save()
        self.set_counts()
        response = self.client.post(url, data=post_data)
        self.assertEqual(response.status_code, 302)  # redirect
        self.compare_counts(num_changelog=1)
        job.refresh_from_db()
        self.assertRedirects(response, redir_url)
        self.check_job_invalidated(job, True, client)

    @patch.object(Permissions, "is_collaborator")
    @patch.object(Permissions, "has_write_access")
    @patch.object(Permissions, "can_view_repo")
    def test_invalidate_pr_author(self, mock_view, mock_write, mock_collab):
        mock_view.return_value = True
        mock_write.return_value = False
        mock_collab.return_value = True
        job = utils.create_job()
        author = utils.create_user_with_token(name="pr_author")
        pr = utils.create_pr(repo=job.recipe.repository)
        pr.username = author.name
        pr.save()
        job.event.pull_request = pr
        job.event.save()
        url = reverse("ci:invalidate", args=[job.pk])
        event_url = reverse("ci:invalidate_event", args=[job.event.pk])

        # signed in without write access and not the author
        other = utils.create_user_with_token(name="other")
        utils.simulate_login(self.client.session, other)
        self.set_counts()
        response = self.client.post(url)
        self.assertEqual(response.status_code, 403)  # forbidden
        response = self.client.post(event_url)
        self.assertEqual(response.status_code, 302)  # redirect with error message
        self.compare_counts()

        # the author can't invalidate if they aren't a collaborator
        utils.simulate_login(self.client.session, author)
        mock_collab.return_value = False
        self.set_counts()
        response = self.client.post(url)
        self.assertEqual(response.status_code, 403)  # forbidden
        response = self.client.post(event_url)
        self.assertEqual(response.status_code, 302)  # redirect with error message
        self.compare_counts()

        # the author can invalidate if they are a collaborator
        mock_collab.return_value = True
        self.set_counts()
        response = self.client.post(url)
        self.assertEqual(response.status_code, 302)  # redirect
        self.compare_counts(ready=1, invalidated=1, num_changelog=1)
        self.check_job_invalidated(job)

        self.set_counts()
        response = self.client.post(event_url)
        self.assertEqual(response.status_code, 302)  # redirect
        self.compare_counts(num_changelog=1)

    @patch.object(Permissions, "is_collaborator")
    @patch.object(Permissions, "has_write_access")
    @patch.object(Permissions, "can_view_repo")
    def test_cancel_pr_author(self, mock_view, mock_write, mock_collab):
        mock_view.return_value = True
        mock_write.return_value = False
        mock_collab.return_value = True
        job = utils.create_job()
        author = utils.create_user_with_token(name="pr_author")
        pr = utils.create_pr(repo=job.recipe.repository)
        pr.username = author.name
        pr.save()
        job.event.pull_request = pr
        job.event.save()
        url = reverse("ci:cancel_job", args=[job.pk])
        event_url = reverse("ci:cancel_event", args=[job.event.pk])

        # signed in without write access and not the author
        other = utils.create_user_with_token(name="other")
        utils.simulate_login(self.client.session, other)
        self.set_counts()
        response = self.client.post(url)
        self.assertEqual(response.status_code, 403)  # forbidden
        response = self.client.post(event_url)
        self.assertEqual(response.status_code, 302)  # redirect with error message
        self.compare_counts()

        # the author can't cancel if they aren't a collaborator
        utils.simulate_login(self.client.session, author)
        mock_collab.return_value = False
        self.set_counts()
        response = self.client.post(url)
        self.assertEqual(response.status_code, 403)  # forbidden
        response = self.client.post(event_url)
        self.assertEqual(response.status_code, 302)  # redirect with error message
        self.compare_counts()

        # the author can cancel if they are a collaborator
        mock_collab.return_value = True
        self.set_counts()
        response = self.client.post(url)
        self.assertEqual(response.status_code, 302)  # redirect
        self.compare_counts(
            canceled=1,
            events_canceled=1,
            num_events_completed=1,
            num_jobs_completed=1,
            num_changelog=1,
        )
        job.refresh_from_db()
        self.assertEqual(job.status, models.JobStatus.CANCELED)

        # but needs write access on other events
        job.event.cause = models.Event.PUSH
        job.event.save()
        self.set_counts()
        response = self.client.post(event_url)
        self.assertEqual(response.status_code, 302)  # redirect with error message
        self.compare_counts()

    @patch.object(Permissions, "is_server_admin")
    def test_prioritize(self, mock_collab):
        # only post is allowed
        url = reverse("ci:prioritize", args=[1000])
        self.set_counts()
        response = self.client.get(url)
        self.assertEqual(response.status_code, 405)  # not allowed
        self.compare_counts()

        # invalid job
        self.set_counts()
        response = self.client.post(url)
        self.assertEqual(response.status_code, 404)  # not found
        self.compare_counts()

        step_result = utils.create_step_result()
        job = step_result.job
        job.event.pull_request = utils.create_pr()
        job.event.comments_url = "some url"
        job.event.save()
        repo = job.recipe.repository
        repo.active = True
        repo.save()

        # can't invalidate
        mock_collab.return_value = False
        url = reverse("ci:prioritize", args=[job.pk])
        self.set_counts()
        response = self.client.post(url)
        self.assertEqual(response.status_code, 403)  # forbidden
        self.compare_counts()

        # valid
        client = utils.create_client()
        job.client = client
        job.save()
        self.assertIsNone(job.prioritized)
        post_data = {"comment": "some comment"}

        # private repo
        self.set_counts()
        self.check_private_repo(url, type="post")
        self.compare_counts()

        # is admin
        mock_collab.return_value = True
        self.set_counts()
        response = self.client.post(url, data=post_data)
        self.assertEqual(response.status_code, 302)  # redirect
        self.compare_counts(num_changelog=1)
        job.refresh_from_db()
        redir_url = reverse("ci:view_job", args=[job.pk])
        self.assertRedirects(response, redir_url)
        self.assertIsNotNone(job.prioritized)

    @override_settings(PERMISSION_CACHE_TIMEOUT=0)
    def test_view_profile(self):
        # invalid git server
        response = self.client.get(reverse("ci:view_profile", args=[1000, "no_exist"]))
        self.assertEqual(response.status_code, 404)

        # not signed in should redirect to sign in
        server = utils.create_git_server()
        response = self.client.get(
            reverse("ci:view_profile", args=[server.host_type, server.name])
        )
        self.assertEqual(response.status_code, 302)  # redirect

        user = utils.get_test_user()
        repo1 = utils.create_repo(name="repo1", user=user, active=True)
        repo2 = utils.create_repo(name="repo2", user=user, active=True)
        repo3 = utils.create_repo(name="repo3", user=user, active=True)
        utils.create_recipe(name="r1", user=user, repo=repo1)
        utils.create_recipe(name="r1b", user=user, repo=repo1)
        utils.create_recipe(name="r2", user=user, repo=repo2)
        utils.create_recipe(name="r3", user=user, repo=repo3)

        # signed in
        utils.simulate_login(self.client.session, user)
        response = self.client.get(
            reverse("ci:view_profile", args=[user.server.host_type, user.server.name])
        )
        self.assertEqual(response.status_code, 200)
        recipes_by_repo = response.context["recipes_by_repo"]
        self.assertEqual([len(r) for r in recipes_by_repo], [2, 1, 1])

    @patch.object(api.GitHubAPI, "has_write_access")
    @patch.object(api.GitHubAPI, "is_collaborator")
    @override_settings(PERMISSION_CACHE_TIMEOUT=0)
    def test_activate_event(self, mock_collab, mock_write):
        # only posts are allowed
        response = self.client.get(reverse("ci:activate_event", args=[1000]))
        self.assertEqual(response.status_code, 405)

        response = self.client.post(reverse("ci:activate_event", args=[1000]))
        self.assertEqual(response.status_code, 404)

        job = utils.create_job()
        job.active = False
        job.save()

        # needs to be active to view
        repo = job.event.base.repo()
        repo.active = True
        repo.save()

        self.set_counts()
        response = self.client.post(reverse("ci:activate_event", args=[job.event.pk]))
        self.compare_counts()
        # not signed in
        self.assertEqual(response.status_code, 403)

        # private repo
        self.set_counts()
        self.check_private_repo(
            reverse("ci:activate_event", args=[job.event.pk]), type="post"
        )
        self.compare_counts()

        user = utils.get_test_user()
        utils.simulate_login(self.client.session, user)
        mock_collab.return_value = True
        mock_write.return_value = False
        self.set_counts()
        response = self.client.post(reverse("ci:activate_event", args=[job.event.pk]))
        self.compare_counts()
        # a collaborator without write access
        self.assertEqual(response.status_code, 403)

        mock_write.return_value = True
        # write access
        self.set_counts()
        response = self.client.post(reverse("ci:activate_event", args=[job.event.pk]))
        self.compare_counts(ready=1, active=1, num_changelog=1)
        self.assertEqual(response.status_code, 302)  # redirect
        job.refresh_from_db()
        self.assertTrue(job.active)

        # no jobs to activate
        self.set_counts()
        response = self.client.post(reverse("ci:activate_event", args=[job.event.pk]))
        self.compare_counts()
        self.assertEqual(response.status_code, 302)  # redirect
        job.refresh_from_db()
        self.assertTrue(job.active)

    @patch.object(api.GitHubAPI, "has_write_access")
    @patch.object(api.GitHubAPI, "is_collaborator")
    @override_settings(PERMISSION_CACHE_TIMEOUT=0)
    def test_activate_job(self, mock_collab, mock_write):
        # only posts are allowed
        response = self.client.get(reverse("ci:activate_job", args=[1000]))
        self.assertEqual(response.status_code, 405)

        response = self.client.post(reverse("ci:activate_job", args=[1000]))
        self.assertEqual(response.status_code, 404)

        job = utils.create_job()
        job.active = False
        job.save()

        # needs to be active to view
        repo = job.event.base.repo()
        repo.active = True
        repo.save()

        self.set_counts()
        url = reverse("ci:activate_job", args=[job.pk])
        self.assertEqual(job.event.base.branch.status, models.JobStatus.NOT_STARTED)
        response = self.client.post(url)
        self.compare_counts()
        # not signed in
        self.assertEqual(response.status_code, 403)

        # private repo
        self.set_counts()
        self.check_private_repo(url, type="post")
        self.compare_counts()

        user = utils.get_test_user()
        utils.simulate_login(self.client.session, user)
        mock_collab.return_value = True
        mock_write.return_value = False
        self.set_counts()
        response = self.client.post(url)
        self.compare_counts()
        # a collaborator without write access
        job = models.Job.objects.get(pk=job.pk)
        self.assertEqual(response.status_code, 403)
        self.assertFalse(job.active)

        mock_write.return_value = True
        # write access
        self.set_counts()
        response = self.client.post(url)
        self.compare_counts(ready=1, active=1, num_changelog=1)
        self.assertEqual(response.status_code, 302)  # redirect
        job.refresh_from_db()
        self.assertTrue(job.active)

        # make sure activating a job doesn't mark it as ready
        r1 = utils.create_recipe(name="r1")
        job.recipe.depends_on.add(r1)
        j1 = utils.create_job(recipe=r1)
        job.active = False
        job.ready = False
        job.save()
        j1.active = False
        j1.ready = False
        j1.save()
        self.set_counts()
        response = self.client.post(url)
        self.compare_counts(active=1, num_changelog=1)
        self.assertEqual(response.status_code, 302)  # redirect
        job.refresh_from_db()
        self.assertTrue(job.active)
        self.assertFalse(job.ready)

        # now it should be marked as ready
        j1.ready = True
        j1.complete = True
        j1.status = models.JobStatus.SUCCESS
        j1.save()
        job.ready = False
        job.active = False
        job.save()
        self.set_counts()
        response = self.client.post(url)
        # The branch is now set to RUNNING since there is an already finished job
        self.compare_counts(ready=1, active=1, num_changelog=1, active_branches=1)
        self.assertEqual(response.status_code, 302)  # redirect
        job.refresh_from_db()
        job.event.base.branch.refresh_from_db()
        self.assertEqual(job.event.base.branch.status, models.JobStatus.RUNNING)
        self.assertTrue(job.active)
        self.assertTrue(job.ready)

        # Calling activate on an already active job shouldn't do anything
        self.set_counts()
        response = self.client.post(url)
        self.compare_counts()
        self.assertEqual(response.status_code, 302)  # redirect

    @override_settings(PERMISSION_CACHE_TIMEOUT=0)
    def test_get_job_results(self):
        # bad pk
        url = reverse("ci:job_results", args=[1000])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)

        user = utils.get_test_user()
        job = utils.create_job(user=user)
        step = utils.create_step(recipe=job.recipe, filename="common/1.sh")
        sr = utils.create_step_result(job=job, step=step)
        sr.output = "some output"
        sr.save()
        utils.create_step_environment(step=step)

        # needs to be active to view
        repo = job.recipe.repository
        repo.active = True
        repo.save()

        url = reverse("ci:job_results", args=[job.pk])
        response = self.client.get(url)
        # owner doesn't have permission
        self.assertEqual(response.status_code, 403)

        # logged in, should get the results
        utils.simulate_login(self.client.session, user)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

        self.check_private_repo(url)

    def test_mooseframework(self):
        # no moose repo
        response = self.client.get(reverse("ci:mooseframework"))
        self.assertEqual(response.status_code, 200)

        user = utils.create_user(name="idaholab")
        repo = utils.create_repo(name="moose", user=user)
        utils.create_pr(repo=repo)
        # no master/devel branches
        response = self.client.get(reverse("ci:mooseframework"))
        self.assertEqual(response.status_code, 200)
        utils.create_branch(name="master", repo=repo)
        utils.create_branch(name="devel", repo=repo)
        # should be good
        response = self.client.get(reverse("ci:mooseframework"))
        self.assertEqual(response.status_code, 200)

    def test_scheduled(self):
        utils.create_event()
        response = self.client.get(reverse("ci:scheduled"))
        self.assertEqual(response.status_code, 200)

    @override_settings(PERMISSION_CACHE_TIMEOUT=0)
    def test_get_user_repos_info(self):
        request = self.factory.get("/")
        request.session = self.client.session
        repos = []
        for i in range(3):
            repo = utils.create_repo(name="repo%s" % i)
            repo.active = True
            repo.save()
            branch = utils.create_branch(name="branch0", user=repo.user, repo=repo)
            branch.status = models.JobStatus.SUCCESS
            branch.save()
            ev = utils.create_event(branch1=branch, branch2=branch, user=repo.user)
            utils.create_job(event=ev, user=repo.user)
            repos.append(repo)

        # user not logged in
        repo_status, evinfo, default = views.get_user_repos_info(request)
        self.assertEqual(len(repo_status), 3)
        self.assertEqual(len(evinfo), 3)
        self.assertFalse(default)

        # user not logged in, default enforced
        request = self.factory.get("/?default")
        request.session = self.client.session
        repo_status, evinfo, default = views.get_user_repos_info(request)
        self.assertEqual(len(repo_status), 3)
        self.assertEqual(len(evinfo), 3)
        self.assertTrue(default)

        request = self.factory.get("/")
        user = repos[0].user
        utils.simulate_login(self.client.session, user)
        request.session = self.client.session
        # user is logged in but no prefs set
        repo_status, evinfo, default = views.get_user_repos_info(request)
        self.assertEqual(len(repo_status), 3)
        self.assertEqual(len(evinfo), 3)
        self.assertFalse(default)

        # user is logged in, add repos to prefs
        for i in range(3):
            user.preferred_repos.add(repos[i])
            repo_status, evinfo, default = views.get_user_repos_info(request)
            self.assertEqual(len(repo_status), i + 1)
            self.assertEqual(len(evinfo), i + 1)
            self.assertFalse(default)

        # user has one pref but default is enforced
        user.preferred_repos.clear()
        user.preferred_repos.add(repos[0])
        request = self.factory.get("/?default")
        request.session = self.client.session
        repo_status, evinfo, default = views.get_user_repos_info(request)
        self.assertEqual(len(repo_status), 3)
        self.assertEqual(len(evinfo), 3)
        self.assertTrue(default)

        # no repos with the active servers
        with self.settings(
            INSTALLED_GITSERVERS=[utils.github_config(hostname="server_does_not_exist")]
        ):
            user.preferred_repos.clear()
            user.preferred_repos.add(repos[0])
            request = self.factory.get("/")
            request.session = self.client.session
            repo_status, evinfo, default = views.get_user_repos_info(request)
            viewable_repos = Permissions.viewable_repos(request.session)
            self.assertEqual(len(viewable_repos), 0)
            self.assertEqual(len(repo_status), 0)
            self.assertEqual(len(evinfo), 0)
            self.assertFalse(default)

        # Back to the default server with the one preference
        request = self.factory.get("/")
        request.session = self.client.session
        viewable_repos = Permissions.viewable_repos(request.session)
        self.assertEqual(len(viewable_repos), 3)
        repo_status, evinfo, default = views.get_user_repos_info(request)
        self.assertEqual(len(repo_status), 1)
        self.assertEqual(len(evinfo), 1)
        self.assertFalse(default)

        # only one repos visible with the default
        with patch.object(Permissions, "viewable_repos") as mock_can_view_repo:
            mock_can_view_repo.return_value = [repos[1].id]
            request = self.factory.get("/?default")
            request.session = self.client.session
            repo_status, evinfo, default = views.get_user_repos_info(request)
            self.assertEqual(len(repo_status), 1)
            self.assertEqual(len(evinfo), 1)
            self.assertEqual(repo_status[0]["id"], repos[1].id)

    def test_user_repo_settings(self):
        """
        testing ci:user_repo_settings
        """
        repos = []
        for i in range(3):
            repo = utils.create_repo(name="repo%s" % i)
            repo.active = True
            repo.save()
            repos.append(repo)
        # not signed in
        url = reverse("ci:user_repo_settings")
        self.set_counts()
        response = self.client.get(url)
        self.compare_counts()
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "form")

        user = repos[0].user
        utils.simulate_login(self.client.session, user)
        self.set_counts()
        response = self.client.get(url)
        self.compare_counts()
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "form")

        # post an invalid form
        self.set_counts()
        response = self.client.post(url, {})
        self.assertEqual(response.status_code, 200)
        self.compare_counts()

        # post a valid form
        self.set_counts()
        response = self.client.post(url, {"repositories": [repos[0].pk, repos[1].pk]})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(user.preferred_repos.count(), 2)
        self.compare_counts(repo_prefs=2)

        # post again with the same recipes
        self.set_counts()
        response = self.client.post(url, {"repositories": [repos[2].pk]})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(user.preferred_repos.count(), 1)
        self.compare_counts(repo_prefs=-1)

    def test_branch_status(self):
        # only GET allowed
        url = reverse("ci:branch_status", args=[1000])
        response = self.client.post(url)
        self.assertEqual(response.status_code, 405)

        # bad pk
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)

        # Not active
        branch = utils.create_branch()
        url = reverse("ci:branch_status", args=[branch.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)

        # OK
        branch.status = models.JobStatus.SUCCESS
        branch.save()
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "image/svg+xml")

    def test_repo_branch_status(self):
        # only GET allowed
        args = ["owner", "repo", "branch"]
        url = reverse("ci:repo_branch_status", args=args)
        response = self.client.post(url)
        self.assertEqual(response.status_code, 405)

        # bad branch
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)

        # Not active
        branch = utils.create_branch()
        args = [branch.repository.user.name, branch.repository.name, branch.name]
        url = reverse("ci:repo_branch_status", args=args)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)

        # OK
        branch.status = models.JobStatus.SUCCESS
        branch.save()
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "image/svg+xml")

    @override_settings(PERMISSION_CACHE_TIMEOUT=0)
    def test_view_user(self):
        user = utils.create_user()
        url = reverse("ci:view_user", args=["no_exist"])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)

        url = reverse("ci:view_user", args=[user.name])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

        ev = utils.create_event()
        pr = utils.create_pr()
        pr.username = user.name
        pr.save()
        ev.pull_request = pr
        ev.save()
        utils.create_job(event=ev)
        repo = pr.repository
        repo.active = True
        repo.save()

        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn(f'id="repo_desc_{repo.id}"', content)
        self.assertIn(f'id="event_{ev.id}"', content)

        with patch.object(Permissions, "viewable_repos") as mock_can_view_repo:
            mock_can_view_repo.return_value = []
            response = self.client.get(url)
            content = response.content.decode()
            self.assertNotIn(f'id="repo_desc_{repo.id}"', content)
            self.assertNotIn(f'id="event_{ev.id}"', content)

    @override_settings(PERMISSION_CACHE_TIMEOUT=0)
    def test_render_unauthorized_repo(self):
        repo = utils.create_repo(active=True)

        # public repo, can view
        self.assertTrue(repo.public())
        request = self.factory.get("/")
        request.session = self.client.session
        response = views.render_unauthorized_repo(request, repo)
        self.assertEqual(response, None)

        # private repo, not logged in
        not_found = self.client.get("/does_not_exist/").content.decode()
        request = self.factory.get("/does_not_exist/")
        request.session = self.client.session
        with patch.object(models.Repository, "public") as mock_public:
            mock_public.return_value = False
            response = views.render_unauthorized_repo(request, repo)
            self.assertEqual(response.status_code, 404)
            self.assertEqual(response.content.decode(), not_found)

        # private repo, logged in
        with patch.object(models.Repository, "public") as mock_public:
            mock_public.return_value = False
            user = utils.get_test_user()
            utils.simulate_login(self.client.session, user)
            request = self.factory.get("/")
            request.session = self.client.session
            response = views.render_unauthorized_repo(request, repo)
            self.assertEqual(response.status_code, 404)
            self.assertIn("Page not found", response.content.decode())

    def test_page_not_found(self):
        def get(name, pk):
            response = self.client.get(reverse(name, args=[pk]))
            self.assertEqual(response.status_code, 404)
            self.assertTemplateUsed(response, "ci/404.html")
            return response.content.decode()

        deleted_msg = "no longer exists. It was most likely deleted due to its age"
        policy_msg = "Pull request events and their jobs are deleted automatically"

        # Not a page for a purgeable object
        response = self.client.get("/does_not_exist/")
        self.assertEqual(response.status_code, 404)
        content = response.content.decode()
        self.assertIn("the requested page could not be found", content)
        self.assertNotIn(policy_msg, content)

        # No pull requests have ever existed
        models.PullRequest.objects.all().delete()
        content = get("ci:view_pr", 1)
        self.assertIn("This pull request does not exist.", content)
        self.assertIn(policy_msg, content)

        # Below the largest pk, so it most likely existed
        old_ev = utils.create_event(commit1="old")
        old_job = utils.create_job(event=old_ev)
        new_job = utils.create_job(event=utils.create_event(commit1="new"))
        old_ev_pk, old_job_pk = old_ev.pk, old_job.pk
        old_ev.delete()
        content = get("ci:view_event", old_ev_pk)
        self.assertIn("This event %s" % deleted_msg, content)
        self.assertIn(policy_msg, content)
        for name in ["ci:view_job", "ci:job_results"]:
            self.assertIn("This job %s" % deleted_msg, get(name, old_job_pk))

        # Above the largest pk, so it never existed
        self.assertIn("This job does not exist.", get("ci:view_job", new_job.pk + 1))
