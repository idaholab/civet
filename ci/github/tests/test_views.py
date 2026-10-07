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
from django.urls import reverse
from ci import models
from ci.tests import utils
from os import path
from mock import patch
import hashlib
import hmac
import json
from django.test import override_settings
from ci.tests import DBTester
from requests_oauthlib import OAuth2Session


def sign(body, secret):
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return "sha256=%s" % digest


@override_settings(INSTALLED_GITSERVERS=[utils.github_config()])
class Tests(DBTester.DBTester):
    def setUp(self):
        super(Tests, self).setUp()
        self.create_default_recipes()
        self.hook = utils.create_webhook(repo=self.repo, build_user=self.build_user)
        self.url = reverse("ci:github:webhook", args=[self.hook.hook_id])

    def get_data(self, fname):
        p = "{}/{}".format(path.dirname(__file__), fname)
        with open(p, "r") as f:
            contents = f.read()
            return contents

    def client_post(self, url, body, signature=None, secret=None):
        """
        Post the raw body, signed with the secret (by default the webhook's)
        unless a signature is given.
        A signature of "" sends no signature header.
        """
        if signature is None:
            signature = sign(body, secret or self.hook.secret)
        headers = {}
        if signature:
            headers["X-Hub-Signature-256"] = signature
        return self.client.post(
            url, body, content_type="application/json", headers=headers
        )

    def client_post_json(self, url, data, signature=None, secret=None):
        json_data = json.dumps(data).encode("utf-8")
        return self.client_post(url, json_data, signature=signature, secret=secret)

    def test_webhook(self):
        # only post allowed
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 405)  # not allowed

        # no webhook
        url = reverse("ci:github:webhook", args=["unknown"])
        data = {"key": "value"}
        response = self.client_post_json(url, data)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.content, b"Error")

        # The old URLs with the build key are no longer accepted
        url = reverse("ci:github:webhook", args=[str(self.build_user.build_key)])
        response = self.client_post_json(url, data)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.content, b"Error")

        # not json
        response = self.client_post(self.url, b"not json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.content, b"Bad json in github webhook request")

        # unknown json
        response = self.client_post_json(self.url, data)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.content, b"Unknown post to github hook")

        # user with no recipes
        user = utils.create_user(name="no_recipes", server=self.server)
        hook = utils.create_webhook(repo=self.repo, build_user=user)
        url = reverse("ci:github:webhook", args=[hook.hook_id])
        response = self.client_post_json(url, data, secret=hook.secret)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.content, b"Error")

    def test_webhook_signature(self):
        ping = json.loads(self.get_data("ping.json"))
        body = json.dumps(ping).encode("utf-8")

        # Properly signed
        response = self.client_post(self.url, body)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"OK")

        # Another webhook for the same build user has its own ID and secret
        other_repo = utils.create_repo(name="other_repo", user=self.owner)
        other_hook = utils.create_webhook(repo=other_repo, build_user=self.build_user)
        self.assertNotEqual(other_hook.secret, self.hook.secret)
        self.assertNotEqual(other_hook.hook_id, self.hook.hook_id)

        bad_signatures = [
            "",  # no header
            "sha256=",
            "sha256=1234",
            "sha256=é",
            sign(body, "wrong secret"),
            sign(body, other_hook.secret),
            sign(body + b" ", self.hook.secret),
            sign(body, self.hook.secret).replace("sha256=", "sha1="),
            sign(body, self.hook.secret).upper(),
        ]
        # Unsigned or badly signed requests are rejected and nothing gets created
        bad_url = reverse("ci:github:webhook", args=["unknown"])
        self.set_counts()
        for signature in bad_signatures:
            for url in [self.url, bad_url]:
                response = self.client_post(url, body, signature=signature)
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.content, b"Error")
        self.compare_counts()

        # A new secret replaces the old one
        old_signature = sign(body, self.hook.secret)
        self.hook.secret = models.generate_webhook_secret()
        self.hook.save()
        response = self.client_post(self.url, body, signature=old_signature)
        self.assertEqual(response.status_code, 400)
        response = self.client_post(self.url, body)
        self.assertEqual(response.status_code, 200)

        # A webhook for a GitLab repository can't be used here
        gitlab_server = utils.create_git_server(
            name="gitlab_server", host_type=settings.GITSERVER_GITLAB
        )
        gitlab_user = utils.create_user(name="gitlab_build", server=gitlab_server)
        gitlab_owner = utils.create_user(name="gitlab_owner", server=gitlab_server)
        gitlab_repo = utils.create_repo(name="gitlab_repo", user=gitlab_owner)
        utils.create_recipe(user=gitlab_user, repo=gitlab_repo)
        gitlab_hook = utils.create_webhook(repo=gitlab_repo, build_user=gitlab_user)
        url = reverse("ci:github:webhook", args=[gitlab_hook.hook_id])
        response = self.client_post(url, body, secret=gitlab_hook.secret)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.content, b"Error")

    @patch.object(OAuth2Session, "post")
    @patch.object(OAuth2Session, "get")
    @patch.object(OAuth2Session, "delete")
    def test_webhook_other_repository(self, mock_del, mock_get, mock_post):
        """
        A signed payload for a different repository than the webhook's
        is rejected, since the secret is only for the webhook's repository.
        """
        other_repo = utils.create_repo(name="other_repo", user=self.owner)
        other_branch = utils.create_branch(name="devel", repo=other_repo)
        for recipe in models.Recipe.objects.filter(repository=self.repo):
            utils.create_recipe(
                name=recipe.name,
                user=self.build_user,
                repo=other_repo,
                branch=other_branch if recipe.branch else None,
                cause=recipe.cause,
            )
        mock_get.return_value = utils.Response(
            [{"name": "1.0", "commit": {"sha": "1234"}}]
        )

        push = json.loads(self.get_data("push_01.json"))
        push["repository"]["owner"]["name"] = self.owner.name
        push["repository"]["name"] = other_repo.name
        push["ref"] = "refs/heads/devel"

        pr = json.loads(self.get_data("pr_open_01.json"))
        pr["pull_request"]["base"]["repo"]["owner"]["login"] = self.owner.name
        pr["pull_request"]["base"]["repo"]["name"] = other_repo.name

        release = json.loads(self.get_data("release.json"))
        release["repository"]["owner"]["login"] = self.owner.name
        release["repository"]["name"] = other_repo.name
        release["release"]["target_commitish"] = "devel"

        self.set_counts()
        for data in [push, pr, release]:
            response = self.client_post_json(self.url, data)
            self.assertEqual(response.status_code, 400)
            self.assertEqual(response.content, b"Error")
        self.compare_counts()
        self.assertEqual(mock_get.call_count, 0)
        self.assertEqual(mock_del.call_count, 0)
        self.assertEqual(mock_post.call_count, 0)

        # The same payload is fine with the other repository's webhook
        hook = utils.create_webhook(repo=other_repo, build_user=self.build_user)
        url = reverse("ci:github:webhook", args=[hook.hook_id])
        response = self.client_post_json(url, push, secret=hook.secret)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"OK")
        self.assertEqual(models.Event.objects.latest().base.repo(), other_repo)

    def test_webhook_too_big(self):
        """
        The body is read before the webhook is looked up, so an oversized
        body gets the same answer for known and unknown webhooks.
        """
        body = json.dumps({"zen": "x" * 100}).encode("utf-8")
        bad_url = reverse("ci:github:webhook", args=["unknown"])
        with self.settings(DATA_UPLOAD_MAX_MEMORY_SIZE=10):
            good = self.client_post(self.url, body)
            bad = self.client_post(bad_url, body)
        self.assertEqual(good.status_code, 400)
        self.assertEqual(good.status_code, bad.status_code)
        self.assertEqual(good.content, bad.content)

    @patch.object(OAuth2Session, "post")
    @patch.object(OAuth2Session, "get")
    @patch.object(OAuth2Session, "delete")
    def test_pull_request(self, mock_del, mock_get, mock_post):
        url = self.url
        changed_files = utils.Response([{"filename": "foo"}])
        mock_get.return_value = changed_files
        mock_del.return_value = utils.Response()
        mock_post.return_value = utils.Response()
        data = self.get_data("pr_open_01.json")
        py_data = json.loads(data)
        py_data["pull_request"]["base"]["repo"]["owner"]["login"] = self.owner.name
        py_data["pull_request"]["base"]["repo"]["name"] = self.repo.name
        py_data["pull_request"]["title"] = "[WIP] testTitle"

        # no events or jobs on a work in progress
        self.set_counts()
        response = self.client_post_json(url, py_data)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"OK")
        self.compare_counts()
        self.assertEqual(mock_get.call_count, 0)
        self.assertEqual(mock_del.call_count, 0)
        self.assertEqual(mock_post.call_count, 0)

        # no events or jobs on a work in progress
        py_data["pull_request"]["title"] = "WIP: testTitle"
        self.set_counts()
        response = self.client_post_json(url, py_data)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"OK")
        self.compare_counts()
        self.assertEqual(mock_get.call_count, 0)
        self.assertEqual(mock_del.call_count, 0)
        self.assertEqual(mock_post.call_count, 0)

        # should produce a job and an event
        py_data["pull_request"]["title"] = "testTitle"
        # The comment URLs are built from the API URL, not taken from the payload
        py_data["pull_request"]["comments_url"] = "https://attacker.example/c"
        py_data["pull_request"]["review_comments_url"] = "https://attacker.example/r"
        self.set_counts()
        mock_get.call_count = 0
        response = self.client_post_json(url, py_data)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"OK")
        self.compare_counts(
            jobs=2,
            ready=1,
            events=1,
            commits=2,
            users=1,
            repos=1,
            branches=1,
            prs=1,
            active=2,
            active_repos=1,
        )
        ev = models.Event.objects.latest()
        self.assertEqual(ev.trigger_user, py_data["pull_request"]["user"]["login"])
        self.assertEqual(
            ev.pull_request.username, py_data["pull_request"]["user"]["login"]
        )
        pr_num = py_data["number"]
        self.assertEqual(
            ev.comments_url,
            "https://<api_url>/repos/%s/%s/issues/%s/comments"
            % (self.owner.name, self.repo.name, pr_num),
        )
        self.assertEqual(
            ev.pull_request.review_comments_url,
            "https://<api_url>/repos/%s/%s/pulls/%s/comments"
            % (self.owner.name, self.repo.name, pr_num),
        )
        self.assertEqual(mock_get.call_count, 1)  # for changed files
        self.assertEqual(mock_del.call_count, 0)
        self.assertEqual(mock_post.call_count, 0)

        # should just close the event
        py_data["action"] = "closed"
        mock_get.call_count = 0
        self.set_counts()
        response = self.client_post_json(url, py_data)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"OK")
        self.compare_counts(pr_closed=True)
        self.assertEqual(mock_get.call_count, 0)  # changed files aren't needed
        self.assertEqual(mock_del.call_count, 0)
        self.assertEqual(mock_post.call_count, 0)

        # should just open the same event
        py_data["action"] = "reopened"
        mock_get.call_count = 0
        self.set_counts()
        response = self.client_post_json(url, py_data)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"OK")
        self.compare_counts()
        # changed files come from the existing event
        self.assertEqual(mock_get.call_count, 0)
        self.assertEqual(mock_del.call_count, 0)
        self.assertEqual(mock_post.call_count, 0)
        ev.refresh_from_db()
        self.assertEqual(ev.get_changed_files(), ["foo"])

        # nothing should change
        py_data["action"] = "labeled"
        mock_get.call_count = 0
        self.set_counts()
        response = self.client_post_json(url, py_data)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"OK")
        self.compare_counts()
        self.assertEqual(mock_get.call_count, 0)
        self.assertEqual(mock_del.call_count, 0)
        self.assertEqual(mock_post.call_count, 0)

        # nothing should change
        py_data["action"] = "<script>bad_action</script>"
        self.set_counts()
        response = self.client_post_json(url, py_data)
        self.assertEqual(response.status_code, 400)
        # The error isn't echoed back, only logged
        self.assertEqual(response.content, b"Error")
        self.assertEqual(response["Content-Type"], "text/plain")
        self.compare_counts()
        self.assertEqual(mock_get.call_count, 0)
        self.assertEqual(mock_del.call_count, 0)
        self.assertEqual(mock_post.call_count, 0)

        # on synchronize we also remove labels on the PR
        py_data["action"] = "synchronize"
        with self.settings(
            INSTALLED_GITSERVERS=[utils.github_config(remote_update=True)]
        ):
            label_name = self.server.server_config()["remove_pr_label_prefix"][0]
            mock_get.return_value = None
            remove_label = utils.Response([{"name": label_name}])
            mock_get.side_effect = [remove_label, changed_files]
            mock_del.return_value = utils.Response()
            self.set_counts()
            response = self.client_post_json(url, py_data)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.content, b"OK")
            self.compare_counts()
            # 1 in remove_pr_todo_labels, changed files come from the existing event
            self.assertEqual(mock_get.call_count, 1)
            self.assertEqual(mock_del.call_count, 1)  # for remove_pr_todo_labels
            self.assertEqual(mock_post.call_count, 0)

            # new sha, new event. The labels come from the payload.
            # The trigger user is whoever pushed, not the author.
            py_data["pull_request"]["head"]["sha"] = "2345"
            py_data["pull_request"]["labels"] = [{"name": label_name}]
            py_data["sender"]["login"] = "pusher"
            mock_get.side_effect = [changed_files]
            mock_get.call_count = 0
            mock_del.call_count = 0
            self.set_counts()
            response = self.client_post_json(url, py_data)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.content, b"OK")
            self.compare_counts(
                jobs=2,
                ready=1,
                events=1,
                commits=1,
                active=2,
                canceled=2,
                events_canceled=1,
                num_changelog=2,
                num_events_completed=1,
                num_jobs_completed=2,
            )
            self.assertEqual(mock_del.call_count, 1)  # for remove_pr_todo_labels
            self.assertEqual(mock_get.call_count, 1)  # for changed files
            self.assertEqual(mock_post.call_count, 2)  # 2 new jobs pending status
            ev = models.Event.objects.latest()
            self.assertEqual(ev.trigger_user, "pusher")
            self.assertEqual(
                ev.pull_request.username, py_data["pull_request"]["user"]["login"]
            )

    @patch.object(OAuth2Session, "post")
    @patch.object(OAuth2Session, "get")
    @patch.object(OAuth2Session, "delete")
    def test_push(self, mock_del, mock_get, mock_post):
        url = self.url
        data = self.get_data("push_01.json")
        py_data = json.loads(data)
        py_data["repository"]["owner"]["name"] = self.owner.name
        py_data["repository"]["name"] = self.repo.name
        py_data["ref"] = "refs/heads/{}".format(self.branch.name)

        # Everything OK
        self.set_counts()
        response = self.client_post_json(url, py_data)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"OK")
        self.compare_counts(
            jobs=2, ready=1, events=1, commits=2, active=2, active_repos=1
        )
        ev = models.Event.objects.latest()
        self.assertEqual(ev.cause, models.Event.PUSH)
        self.assertEqual(ev.description, "Update README.md")
        self.assertEqual(mock_del.call_count, 0)
        self.assertEqual(mock_get.call_count, 0)
        self.assertEqual(mock_post.call_count, 0)

        py_data["head_commit"]["message"] = "Merge commit '123456789'"
        py_data["after"] = "123456789"
        py_data["before"] = "1"
        self.set_counts()
        response = self.client_post_json(url, py_data)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"OK")
        self.compare_counts(jobs=2, ready=1, events=1, commits=2, active=2)
        ev = models.Event.objects.latest()
        self.assertEqual(ev.description, "Merge commit 123456")
        self.assertEqual(mock_del.call_count, 0)
        self.assertEqual(mock_get.call_count, 0)
        self.assertEqual(mock_post.call_count, 0)

    def test_zen(self):
        url = self.url
        data = self.get_data("ping.json")
        py_data = json.loads(data)
        self.set_counts()
        response = self.client_post_json(url, py_data)
        self.assertEqual(response.status_code, 200)
        self.compare_counts()

    @patch.object(OAuth2Session, "post")
    @patch.object(OAuth2Session, "get")
    @patch.object(OAuth2Session, "delete")
    def test_release(self, mock_del, mock_get, mock_post):
        jdata = [
            {
                "name": "1.0",
                "commit": {"sha": "1234"},
            }
        ]
        mock_get.return_value = utils.Response(jdata)
        url = self.url
        data = self.get_data("release.json")
        py_data = json.loads(data)
        py_data["repository"]["owner"]["login"] = self.owner.name
        py_data["repository"]["name"] = self.repo.name
        py_data["release"]["target_commitish"] = self.branch.name
        self.set_counts()
        response = self.client_post_json(url, py_data)
        self.assertEqual(response.status_code, 200)
        self.compare_counts()
        self.assertEqual(mock_del.call_count, 0)
        self.assertEqual(mock_get.call_count, 1)  # getting SHA
        self.assertEqual(mock_post.call_count, 0)

        # The commit could be a hash, then we assume the branch is master
        py_data["release"]["target_commitish"] = "1" * 40
        mock_get.call_count = 0
        self.set_counts()
        response = self.client_post_json(url, py_data)
        self.assertEqual(response.status_code, 200)
        self.compare_counts()
        self.assertEqual(mock_del.call_count, 0)
        self.assertEqual(mock_get.call_count, 0)
        self.assertEqual(mock_post.call_count, 0)

        rel = utils.create_recipe(
            name="Release1",
            user=self.build_user,
            repo=self.repo,
            branch=self.branch,
            cause=models.Recipe.CAUSE_RELEASE,
        )
        rel1 = utils.create_recipe(
            name="Release with dep",
            user=self.build_user,
            repo=self.repo,
            branch=self.branch,
            cause=models.Recipe.CAUSE_RELEASE,
        )
        rel1.depends_on.add(rel)

        py_data["release"]["target_commitish"] = self.branch.name
        self.set_counts()
        response = self.client_post_json(url, py_data)
        self.assertEqual(response.status_code, 200)
        self.compare_counts(events=1, commits=1, jobs=2, ready=1, active=2)
        self.assertEqual(mock_del.call_count, 0)
        self.assertEqual(mock_get.call_count, 1)  # getting SHA
        self.assertEqual(mock_post.call_count, 0)

        mock_get.call_count = 0
        mock_get.side_effect = Exception("Bam!")
        self.set_counts()
        response = self.client_post_json(url, py_data)
        self.assertEqual(response.status_code, 400)
        self.compare_counts()
        self.assertEqual(mock_del.call_count, 0)
        self.assertEqual(mock_get.call_count, 1)  # getting SHA
        self.assertEqual(mock_post.call_count, 0)
