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
from django.conf import settings
from django.test import override_settings
from django.urls import reverse
from mock import patch
from ci import models
from ci.tests import utils
import os, json
from ci.gitlab import views
from ci.tests import DBTester
from requests_oauthlib import OAuth2Session


class PrResponse(utils.Response):
    def __init__(self, user, repo, commit="1", title="testTitle", *args, **kwargs):
        """
        All the responses all in one dict
        """
        data = {
            "title": title,
            "path_with_namespace": "{}/{}".format(user.name, repo.name),
            "iid": "1",
            "owner": {"username": user.name},
            "name": repo.name,
            "commit": {"id": commit},
            "ssh_url_to_repo": "testUrl",
        }
        super(PrResponse, self).__init__(json_data=data, *args, **kwargs)


class PushResponse(utils.Response):
    def __init__(self, user, repo, *args, **kwargs):
        data = {
            "name": repo.name,
            "namespace": {"name": user.name},
            "path_with_namespace": "%s/%s" % (user.name, repo.name),
        }
        super(PushResponse, self).__init__(data, *args, **kwargs)


@override_settings(INSTALLED_GITSERVERS=[utils.gitlab_config()])
class Tests(DBTester.DBTester):
    def setUp(self):
        super(Tests, self).setUp()
        self.create_default_recipes(server_type=settings.GITSERVER_GITLAB)
        self.hook = utils.create_webhook(repo=self.repo, build_user=self.build_user)
        self.url = reverse("ci:gitlab:webhook", args=[self.hook.hook_id])

    def get_data(self, fname):
        p = "{}/{}".format(os.path.dirname(__file__), fname)
        with open(p, "r") as f:
            contents = f.read()
            return contents

    def get_pr_data(self):
        """
        The merge request data, with this webhook's repository as the target
        """
        pr_data = json.loads(self.get_data("pr_open_01.json"))
        target = pr_data["object_attributes"]["target"]
        target["path_with_namespace"] = "%s/%s" % (self.owner.name, self.repo.name)
        target["namespace"] = self.owner.name
        target["name"] = self.repo.name
        return pr_data

    def client_post(self, url, body, token=None):
        """
        Post the raw body with the given secret token, by default the webhook's.
        A token of "" sends no token header.
        """
        if token is None:
            token = self.hook.secret
        headers = {}
        if token:
            headers["X-Gitlab-Token"] = token
        return self.client.post(
            url, body, content_type="application/json", headers=headers
        )

    def client_post_json(self, url, data, token=None):
        return self.client_post(url, json.dumps(data), token=token)

    def test_webhook(self):
        # only post allowed
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 405)  # not allowed

        # no webhook
        url = reverse("ci:gitlab:webhook", args=["unknown"])
        data = {"key": "value"}
        response = self.client_post_json(url, data)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.content, b"Error")

        # The old URLs with a numeric build key are no longer accepted
        url = reverse("ci:gitlab:webhook", args=["123456789"])
        response = self.client_post_json(url, data)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.content, b"Error")

        # not json
        response = self.client_post(self.url, "not json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.content, b"Bad json in gitlab webhook request")

        # unknown json
        response = self.client_post_json(self.url, data)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.content, b"Unknown post to gitlab hook")

        # user with no recipes
        user = utils.create_user(name="no_recipes", server=self.server)
        hook = utils.create_webhook(repo=self.repo, build_user=user)
        url = reverse("ci:gitlab:webhook", args=[hook.hook_id])
        response = self.client_post_json(url, data, token=hook.secret)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.content, b"Error")

    def test_webhook_token(self):
        data = {"object_kind": "x"}

        # With the right token the request gets processed
        response = self.client_post_json(self.url, data)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.content, b"Unknown post to gitlab hook")

        # Another webhook for the same build user has its own ID and secret
        other_repo = utils.create_repo(name="other_repo", user=self.owner)
        other_hook = utils.create_webhook(repo=other_repo, build_user=self.build_user)
        self.assertNotEqual(other_hook.secret, self.hook.secret)
        self.assertNotEqual(other_hook.hook_id, self.hook.hook_id)

        secret = self.hook.secret
        bad_tokens = [
            "",  # no header
            "wrong token",
            other_hook.secret,
            secret + " ",
            secret[:-1],
            secret.upper(),
            "é",
        ]
        # Requests without the token are rejected and nothing gets created
        bad_url = reverse("ci:gitlab:webhook", args=["unknown"])
        self.set_counts()
        for token in bad_tokens:
            for url in [self.url, bad_url]:
                response = self.client_post_json(url, data, token=token)
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.content, b"Error")
        self.compare_counts()

        # A new secret replaces the old one
        self.hook.secret = models.generate_webhook_secret()
        self.hook.save()
        response = self.client_post_json(self.url, data, token=secret)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.content, b"Error")
        response = self.client_post_json(self.url, data)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.content, b"Unknown post to gitlab hook")

    def test_webhook_github_repo(self):
        """
        A webhook for a GitHub repository is treated like an unknown webhook.
        """
        github_server = utils.create_git_server(
            name="github_server", host_type=settings.GITSERVER_GITHUB
        )
        github_user = utils.create_user(name="github_build", server=github_server)
        repo = utils.create_repo(user=github_user)
        utils.create_recipe(user=github_user, repo=repo)
        hook = utils.create_webhook(repo=repo, build_user=github_user)
        pr = utils.create_pr(repo=repo, number=1)
        pr.closed = False
        pr.save()
        url = reverse("ci:gitlab:webhook", args=[hook.hook_id])
        data = {
            "object_kind": "merge_request",
            "object_attributes": {
                "state": "closed",
                "iid": 1,
                "target": {
                    "path_with_namespace": "%s/%s" % (github_user.name, repo.name),
                    "name": repo.name,
                },
            },
        }
        self.set_counts()
        response = self.client_post_json(url, data, token=hook.secret)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.content, b"Error")
        self.compare_counts()
        pr.refresh_from_db()
        self.assertFalse(pr.closed)

    @patch.object(OAuth2Session, "get")
    def test_webhook_other_repository(self, mock_get):
        """
        A payload for a different repository than the webhook's is rejected,
        since the secret is only for the webhook's repository.
        """
        other_repo = utils.create_repo(name="other_repo", user=self.owner)
        utils.create_recipe(name="Other", user=self.build_user, repo=other_repo)
        utils.create_recipe(
            name="Other push",
            user=self.build_user,
            repo=other_repo,
            branch=utils.create_branch(name="devel", repo=other_repo),
            cause=models.Recipe.CAUSE_PUSH,
        )
        pr = utils.create_pr(repo=other_repo, number=1)
        pr.closed = False
        pr.save()

        # Closing a merge request on the other repository
        pr_data = self.get_pr_data()
        pr_data["object_attributes"]["state"] = "closed"
        pr_data["object_attributes"]["iid"] = 1
        target = pr_data["object_attributes"]["target"]
        target["path_with_namespace"] = "%s/%s" % (self.owner.name, other_repo.name)
        target["name"] = other_repo.name

        # A push to the other repository
        push_data = json.loads(self.get_data("push_01.json"))
        push_data["ref"] = "refs/heads/devel"
        mock_get.return_value = PushResponse(self.owner, other_repo)

        self.set_counts()
        for data in [pr_data, push_data]:
            response = self.client_post_json(self.url, data)
            self.assertEqual(response.status_code, 400)
            self.assertEqual(response.content, b"Error")
        self.compare_counts()
        pr.refresh_from_db()
        self.assertFalse(pr.closed)
        # Only to look up the project of the push
        self.assertEqual(mock_get.call_count, 1)

        # The same payloads are fine with the other repository's webhook
        hook = utils.create_webhook(repo=other_repo, build_user=self.build_user)
        url = reverse("ci:gitlab:webhook", args=[hook.hook_id])
        response = self.client_post_json(url, pr_data, token=hook.secret)
        self.assertEqual(response.status_code, 200)
        pr.refresh_from_db()
        self.assertTrue(pr.closed)
        response = self.client_post_json(url, push_data, token=hook.secret)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(models.Event.objects.latest().base.repo(), other_repo)

    def test_webhook_too_big(self):
        """
        The body is read before the webhook is looked up, so an oversized
        body gets the same answer for known and unknown webhooks.
        """
        body = json.dumps({"object_kind": "x" * 100})
        bad_url = reverse("ci:gitlab:webhook", args=["unknown"])
        with self.settings(DATA_UPLOAD_MAX_MEMORY_SIZE=10):
            good = self.client_post(self.url, body)
            bad = self.client_post(bad_url, body)
        self.assertEqual(good.status_code, 400)
        self.assertEqual(good.status_code, bad.status_code)
        self.assertEqual(good.content, bad.content)

    def test_close_pr(self):
        user = utils.get_test_user(server=self.server)
        repo = utils.create_repo(user=user)
        pr = utils.create_pr(repo=repo, number=1)
        pr.closed = False
        pr.save()
        views.close_pr("foo", "bar", 1, user.server)
        pr.refresh_from_db()
        self.assertFalse(pr.closed)

        views.close_pr(user.name, "bar", 1, user.server)
        pr.refresh_from_db()
        self.assertFalse(pr.closed)

        views.close_pr(user.name, repo.name, 0, user.server)
        pr.refresh_from_db()
        self.assertFalse(pr.closed)

        views.close_pr(user.name, repo.name, 1, user.server)
        pr.refresh_from_db()
        self.assertTrue(pr.closed)

    @patch.object(OAuth2Session, "get")
    def test_pull_request_bad_source(self, mock_get):
        """
        Sometimes the user hasn't given moosetest access to their repository
        and an error occurs. It is hard to check if a successful comment
        has happened but just try to get coverage.
        """
        pr_data = self.get_pr_data()

        # Simulate an error on the server while getting the source branch
        mock_get.return_value = utils.Response(status_code=404)

        self.set_counts()
        response = self.client_post_json(self.url, pr_data)
        self.assertEqual(response.status_code, 400)
        self.compare_counts()
        self.assertEqual(mock_get.call_count, 1)

    @patch.object(OAuth2Session, "post")
    @patch.object(OAuth2Session, "get")
    def test_pull_request_bad_source_comment(self, mock_get, mock_post):
        """
        The comment about the bad source branch goes to the MR on the
        target project, addressed by its path.
        """
        pr_data = self.get_pr_data()
        mock_get.return_value = utils.Response(status_code=404)
        mock_post.return_value = utils.Response()
        config = utils.gitlab_config(remote_update=True)
        with self.settings(INSTALLED_GITSERVERS=[config]):
            self.set_counts()
            response = self.client_post_json(self.url, pr_data)
            self.assertEqual(response.status_code, 400)
            self.compare_counts()
        self.assertEqual(mock_post.call_count, 1)
        self.assertEqual(
            mock_post.call_args.args[0],
            "https://<api_url>/api/v4/projects/%s%%2F%s/merge_requests/1/notes"
            % (self.owner.name, self.repo.name),
        )

    @patch.object(OAuth2Session, "post")
    @patch.object(OAuth2Session, "get")
    def test_pull_request_target_from_webhook(self, mock_get, mock_post):
        """
        The target branch and the comments use the webhook's repository,
        not the target project ID or full path in the payload.
        """
        pr_data = self.get_pr_data()
        attributes = pr_data["object_attributes"]
        attributes["target_project_id"] = 999
        attributes["target"]["path_with_namespace"] = "%s/other" % self.owner.name
        repo_api = "https://<api_url>/api/v4/projects/%s%%2F%s" % (
            self.owner.name,
            self.repo.name,
        )
        mock_post.return_value = utils.Response()
        config = utils.gitlab_config(remote_update=True)
        with self.settings(INSTALLED_GITSERVERS=[config]):
            # The comment about a bad source branch
            mock_get.return_value = utils.Response(status_code=404)
            response = self.client_post_json(self.url, pr_data)
            self.assertEqual(response.status_code, 400)
            self.assertEqual(mock_post.call_count, 1)
            self.assertEqual(
                mock_post.call_args.args[0], "%s/merge_requests/1/notes" % repo_api
            )

            # The target branch
            mock_get.return_value = PrResponse(self.owner, self.repo)
            mock_get.reset_mock()
            self.client_post_json(self.url, pr_data)
            self.assertEqual(
                mock_get.call_args_list[1].args[0],
                "%s/repository/branches/%s" % (repo_api, attributes["target_branch"]),
            )
        for call in mock_get.call_args_list + mock_post.call_args_list:
            self.assertNotIn("999", call.args[0])
            self.assertNotIn("other", call.args[0])

    @patch.object(OAuth2Session, "post")
    @patch.object(OAuth2Session, "get")
    def test_pull_request_bad_ids(self, mock_get, mock_post):
        """
        Project IDs and MR IDs that aren't integers are rejected before
        any request is made, so they can't redirect the API calls.
        """
        mock_get.return_value = utils.Response(status_code=404)
        mock_post.return_value = utils.Response()
        url = self.url
        config = utils.gitlab_config(remote_update=True)
        bad_id = "431560/issues/5/notes?x="
        with self.settings(INSTALLED_GITSERVERS=[config]):
            for key in ["source_project_id", "iid"]:
                pr_data = self.get_pr_data()
                pr_data["object_attributes"][key] = bad_id
                self.set_counts()
                response = self.client_post_json(url, pr_data)
                self.assertEqual(response.status_code, 400)
                self.compare_counts()

            push_data = json.loads(self.get_data("push_01.json"))
            push_data["project_id"] = bad_id
            self.set_counts()
            response = self.client_post_json(url, push_data)
            self.assertEqual(response.status_code, 400)
            self.compare_counts()
        self.assertEqual(mock_get.call_count, 0)
        self.assertEqual(mock_post.call_count, 0)

    @patch.object(OAuth2Session, "get")
    def test_pull_request(self, mock_get):
        """
        Unlike with GitHub, GitLab requires that you
        do a bunch of extra requests to get the needed information.
        Since we don't have authorization we have to mock these up.
        """
        data = self.get_data("pr_open_01.json")
        pr_data = json.loads(data)
        data = self.get_data("files.json")
        file_data = json.loads(data)
        data = self.get_data("user.json")
        user_data = json.loads(data)
        data = self.get_data("project_member.json")
        member_data = json.loads(data)

        # an MR on a different repository than the webhook's is rejected
        pr_response = PrResponse(self.owner, self.repo)
        user_response = utils.Response(json_data=user_data)
        member_response = utils.Response(json_data=member_data)
        full_response = [
            pr_response,
            pr_response,
            user_response,
            member_response,
            utils.Response(json_data=file_data),
            user_response,  # author
        ]
        mock_get.side_effect = full_response
        url = self.url

        self.set_counts()
        response = self.client_post_json(url, pr_data)
        self.assertEqual(response.status_code, 400)
        self.compare_counts()
        self.assertEqual(mock_get.call_count, 0)

        pr_data["object_attributes"]["target"]["path_with_namespace"] = "%s/%s" % (
            self.owner.name,
            self.repo.name,
        )
        pr_data["object_attributes"]["target"]["namespace"] = self.owner.name
        pr_data["object_attributes"]["target"]["name"] = self.repo.name

        # there is a recipe but the PR is a work in progress
        title = "[WIP] testTitle"
        pr_data["object_attributes"]["title"] = title
        mock_get.return_value = PrResponse(self.owner, self.repo, title=title)
        mock_get.side_effect = None
        self.set_counts()
        response = self.client_post_json(url, pr_data)
        self.assertEqual(response.status_code, 200)
        self.compare_counts()

        # there is a recipe but the PR is a work in progress
        title = "WIP: testTitle"
        pr_data["object_attributes"]["title"] = title
        pr_response = PrResponse(self.owner, self.repo, title=title)
        full_response = [
            pr_response,
            pr_response,
            user_response,
            member_response,
            utils.Response(json_data=file_data),
            user_response,  # author
        ]
        mock_get.side_effect = full_response
        self.set_counts()
        response = self.client_post_json(url, pr_data)
        self.assertEqual(response.status_code, 200)
        self.compare_counts()

        # there is a recipe so a job should be made ready
        title = "testTitle"
        pr_data["object_attributes"]["title"] = title
        mock_get.side_effect = full_response
        self.set_counts()
        response = self.client_post_json(url, pr_data)
        self.assertEqual(response.status_code, 200)

        self.compare_counts(
            jobs=2,
            ready=1,
            events=1,
            users=1,
            repos=1,
            branches=2,
            commits=2,
            prs=1,
            active=2,
            active_repos=1,
        )
        ev = models.Event.objects.latest()
        self.assertEqual(ev.jobs.first().ready, True)
        self.assertEqual(ev.pull_request.title, "testTitle")
        self.assertEqual(ev.pull_request.closed, False)
        self.assertEqual(ev.trigger_user, pr_data["user"]["username"])
        # The author is looked up from author_id, not the user that triggered it
        self.assertEqual(ev.pull_request.username, user_data["username"])
        self.assertNotEqual(ev.pull_request.username, ev.trigger_user)
        self.assertTrue(mock_get.call_args[0][0].endswith("/users/231340"))

        # if it is the same commit nothing should happen
        self.set_counts()
        mock_get.side_effect = full_response
        response = self.client_post_json(url, pr_data)
        self.assertEqual(response.status_code, 200)
        self.compare_counts()

        # if the base commit changes but the head commit is
        # the same, nothing should happen
        target_response = PrResponse(self.owner, self.repo, commit="2")
        full_response[1] = target_response
        self.set_counts()
        mock_get.side_effect = full_response
        response = self.client_post_json(url, pr_data)
        self.assertEqual(response.status_code, 200)
        self.compare_counts()

        # if the head commit changes then new jobs should be created
        # and old ones canceled.
        source_response = PrResponse(self.owner, self.repo, commit="2")
        full_response[1] = pr_response
        full_response[0] = source_response
        self.set_counts()
        mock_get.side_effect = full_response
        response = self.client_post_json(url, pr_data)
        self.assertEqual(response.status_code, 200)
        self.compare_counts(
            jobs=2,
            ready=1,
            active=2,
            events=1,
            canceled=2,
            events_canceled=1,
            num_changelog=2,
            num_events_completed=1,
            num_jobs_completed=2,
            commits=1,
        )

        pr_data["object_attributes"]["state"] = "closed"
        self.set_counts()
        mock_get.side_effect = full_response
        response = self.client_post_json(url, pr_data)
        self.assertEqual(response.status_code, 200)
        self.compare_counts(pr_closed=True)

        pr_data["object_attributes"]["state"] = "reopened"
        self.set_counts()
        mock_get.side_effect = full_response
        response = self.client_post_json(url, pr_data)
        self.assertEqual(response.status_code, 200)
        self.compare_counts(pr_closed=False)

        pr_data["object_attributes"]["state"] = "synchronize"
        self.set_counts()
        mock_get.side_effect = full_response
        response = self.client_post_json(url, pr_data)
        self.assertEqual(response.status_code, 200)
        self.compare_counts()

        pr_data["object_attributes"]["state"] = "merged"
        self.set_counts()
        mock_get.side_effect = full_response
        response = self.client_post_json(url, pr_data)
        self.assertEqual(response.status_code, 200)
        self.compare_counts(pr_closed=True)

        pr_data["object_attributes"]["state"] = "<script>unknown</script>"
        self.set_counts()
        mock_get.side_effect = full_response
        response = self.client_post_json(url, pr_data)
        self.assertEqual(response.status_code, 400)
        # The error isn't echoed back, only logged
        self.assertEqual(response.content, b"Error")
        self.assertEqual(response["Content-Type"], "text/plain")
        self.compare_counts(pr_closed=True)

    @patch.object(OAuth2Session, "get")
    def test_push(self, mock_get):
        """
        The push event for GitLab just gives project ids and user ids
        which isn't enough information.
        It does an additional request to get more information about
        the project.
        """
        data = self.get_data("push_01.json")
        push_data = json.loads(data)

        # no recipe so no jobs should be created
        self.set_counts()
        mock_get.return_value = PushResponse(self.owner, self.repo)
        url = self.url
        response = self.client_post_json(url, push_data)
        self.assertEqual(response.status_code, 200)
        self.compare_counts()
        self.assertEqual(response.content, b"OK")

        push_data["ref"] = "refs/heads/%s" % self.branch.name

        self.set_counts()
        response = self.client_post_json(url, push_data)
        self.assertEqual(response.status_code, 200)
        self.compare_counts(
            jobs=2, ready=1, events=1, commits=2, active=2, active_repos=1
        )
        self.assertEqual(response.content, b"OK")

        push_data["commits"] = []

        self.set_counts()
        mock_get.call_count = 0
        response = self.client_post_json(url, push_data)
        self.assertEqual(response.status_code, 200)
        self.compare_counts()
        self.assertEqual(response.content, b"OK")
        self.assertEqual(mock_get.call_count, 0)
