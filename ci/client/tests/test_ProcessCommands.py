
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

import ClientTester
from django.test import override_settings
from ci.client import ProcessCommands
from ci.tests import utils
from ci import models
from ci.github import api
from requests_oauthlib import OAuth2Session
from mock import patch
import re

@override_settings(INSTALLED_GITSERVERS=[utils.github_config(remote_update=True)])
class Tests(ClientTester.ClientTester):
    def test_find_in_output(self):
        s = " Foo=some value"
        r = ProcessCommands.find_in_output(s, "Foo")
        self.assertEqual(r, None)
        s = s.strip()
        r = ProcessCommands.find_in_output(s, "Foo")
        s = "Foo = bar"
        r = ProcessCommands.find_in_output(s, "Foo")
        self.assertEqual(r, None)
        s = "Foo="
        r = ProcessCommands.find_in_output(s, "Foo")
        self.assertEqual(r, "")

        s = "Another line\nFoo=bar"
        r = ProcessCommands.find_in_output(s, "Foo")
        self.assertEqual(r, "bar")

    def create_step_result(self, output):
        result = utils.create_step_result()
        result.output = output
        result.save()
        ev = result.job.event
        ev.pull_request = utils.create_pr()
        ev.pull_request.review_comments_url = "review_comments"
        ev.pull_request.save()
        ev.comments_url = "url"
        ev.save()
        return result

    @patch.object(OAuth2Session, 'post')
    def test_check_submodule_update(self, mock_post):
        result = self.create_step_result("PREVIOUS_LINE\nCIVET_CLIENT_SUBMODULE_UPDATES=1\nNEXT_LINE\n")
        self.assertEqual(ProcessCommands.check_submodule_update(result.job, result.position), True)

    @patch.object(OAuth2Session, 'post')
    @patch.object(OAuth2Session, 'get')
    @patch.object(OAuth2Session, 'delete')
    @patch.object(OAuth2Session, 'patch')
    def test_edit_comment(self, mock_patch, mock_del, mock_get, mock_post):
        user = utils.get_test_user()
        api = user.api()
        mock_get.return_value = utils.Response()
        ProcessCommands.edit_comment(api, user, "some_url", "Some message", "Some re")
        self.assertEqual(mock_get.call_count, 1) # 1 call to get the current comments
        self.assertEqual(mock_del.call_count, 0)
        self.assertEqual(mock_patch.call_count, 0)
        self.assertEqual(mock_post.call_count, 1) # 1 call to post the comment

        # Only 1 existing comment, should just update it
        c0 = {"user": {"login": user.name}, "body": "some message", "url": "url"}
        mock_get.return_value = utils.Response([c0])
        ProcessCommands.edit_comment(api, user, "some_url", "some other message", "some me")
        self.assertEqual(mock_get.call_count, 2)
        self.assertEqual(mock_del.call_count, 0)
        self.assertEqual(mock_patch.call_count, 1) # Updates the existing comment
        self.assertEqual(mock_post.call_count, 1)

        # 2 existing comment, 1 should be deleted and 1 should be updated
        c1 = {"user": {"login": user.name}, "body": "some message 2", "url": "url"}
        mock_get.return_value = utils.Response([c0, c1])
        ProcessCommands.edit_comment(api, user, "some_url", "some other message", "some me")
        self.assertEqual(mock_get.call_count, 3)
        self.assertEqual(mock_del.call_count, 1)
        self.assertEqual(mock_patch.call_count, 2)
        self.assertEqual(mock_post.call_count, 1)

    @patch.object(OAuth2Session, 'post')
    @patch.object(OAuth2Session, 'get')
    @patch.object(OAuth2Session, 'delete')
    def test_ensure_single_new_comment(self, mock_del, mock_get, mock_post):
        user = utils.get_test_user()
        api = user.api()

        # No comments, just create a new one
        mock_get.return_value = utils.Response()
        ProcessCommands.ensure_single_new_comment(api, user, "some_url", "Some message", "Some re")
        self.assertEqual(mock_get.call_count, 1) # 1 call to get existing comments
        self.assertEqual(mock_del.call_count, 0)
        self.assertEqual(mock_post.call_count, 1) # 1 call to create a comment

        # Existing comments, they are deleted and a new one is created
        c0 = {"user": {"login": user.name}, "body": "some message", "url": "url1"}
        c1 = {"user": {"login": user.name}, "body": "some message 2", "url": "url2"}
        mock_get.return_value = utils.Response([c0, c1])
        ProcessCommands.ensure_single_new_comment(api, user, "some_url", "some message", "some me")
        self.assertEqual(mock_get.call_count, 2)
        self.assertEqual(mock_del.call_count, 2)
        self.assertEqual(mock_post.call_count, 2)

    @patch.object(ProcessCommands, 'edit_comment')
    def test_check_post_comment_re(self, mock_edit):
        """
        Make sure the regular expression that is used will be able to match the message
        """
        result = self.create_step_result("PREVIOUS_LINE\nCIVET_CLIENT_POST_MESSAGE=My message")
        request = self.factory.get('/')
        self.assertIs(ProcessCommands.check_post_comment(request, result.job, result.position, True, False), True)
        self.assertEqual(mock_edit.call_count, 1)
        args, kwargs = mock_edit.call_args
        msg = args[3]
        msg_re = args[4]
        self.assertIn("My message", msg)
        self.assertNotEqual(re.search(msg_re, msg), None)

    @patch.object(api.GitHubAPI, 'edit_pr_comment')
    @patch.object(api.GitHubAPI, 'remove_pr_comment')
    @patch.object(api.GitHubAPI, 'pr_comment')
    @patch.object(api.GitHubAPI, 'get_pr_comments')
    def test_check_post_comment(self, mock_get_comments, mock_comment, mock_remove, mock_edit):
        result = self.create_step_result("PREVIOUS_LINE\nCIVET_CLIENT_POST_MESSAGE=My message\nMore text\n")
        request = self.factory.get('/')
        self.assertIs(ProcessCommands.check_post_comment(request, result.job, result.position, False, False), True)
        # args holds the actual arguments to pr_comment. We want the third one which is the message.
        args, kwargs = mock_comment.call_args
        self.assertIn("My message", args[1])
        self.assertNotIn("More text", args[1])
        self.assertEqual(mock_get_comments.call_count, 0)
        self.assertEqual(mock_comment.call_count, 1)
        self.assertEqual(mock_remove.call_count, 0)
        self.assertEqual(mock_edit.call_count, 0)

        mock_get_comments.return_value = []
        self.assertIs(ProcessCommands.check_post_comment(request, result.job, result.position, True, False), True)
        self.assertEqual(mock_get_comments.call_count, 1)
        self.assertEqual(mock_comment.call_count, 2)
        self.assertEqual(mock_remove.call_count, 0)
        self.assertEqual(mock_edit.call_count, 0)

        # These are not really valid comment data
        mock_get_comments.return_value = [{"id": 1}, {"id": 2}]

        self.assertIs(ProcessCommands.check_post_comment(request, result.job, result.position, True, False), True)
        self.assertEqual(mock_get_comments.call_count, 2)
        self.assertEqual(mock_comment.call_count, 2)
        self.assertEqual(mock_remove.call_count, 1)
        self.assertEqual(mock_edit.call_count, 1)

        self.assertIs(ProcessCommands.check_post_comment(request, result.job, result.position, False, True), True)
        self.assertEqual(mock_get_comments.call_count, 3)
        self.assertEqual(mock_comment.call_count, 3)
        self.assertEqual(mock_remove.call_count, 3)
        self.assertEqual(mock_edit.call_count, 1)

        self.assertIs(ProcessCommands.check_post_comment(request, result.job, result.position, False, False), True)

        result.output = "Some other text\nText\n"
        result.save()
        self.assertIs(ProcessCommands.check_post_comment(request, result.job, result.position, False, False), False)
        self.assertEqual(mock_get_comments.call_count, 3)
        self.assertEqual(mock_comment.call_count, 4)
        self.assertEqual(mock_remove.call_count, 3)
        self.assertEqual(mock_edit.call_count, 1)

        msg = "This\nis\nmy\nmultiline\nmessage\n"
        result.output = "PREVIOUS LINE\nCIVET_CLIENT_START_POST_MESSAGE\n%s\nCIVET_CLIENT_END_POST_MESSAGE\nNEXT LINE\n" % msg
        result.save()
        self.assertIs(ProcessCommands.check_post_comment(request, result.job, result.position, False, False), True)
        args, kwargs = mock_comment.call_args
        self.assertIn(msg, args[1])
        self.assertNotIn("PREVIOUS LINE", args[1])
        self.assertNotIn("NEXT LINE", args[1])
        self.assertEqual(mock_get_comments.call_count, 3)
        self.assertEqual(mock_comment.call_count, 5)
        self.assertEqual(mock_remove.call_count, 3)
        self.assertEqual(mock_edit.call_count, 1)

    @patch.object(ProcessCommands, 'check_submodule_update')
    @patch.object(ProcessCommands, 'check_post_comment')
    def test_process_commands(self, mock_post, mock_submodule):
        """
        Hard to test these so just get coverage.
        """
        update_key = "CIVET_CLIENT_SUBMODULE_UPDATES"
        post_key = "CIVET_CLIENT_POST_MESSAGE"
        result = self.create_step_result("PREVIOUS\n%s=libmesh\n%s=My message" % (update_key, post_key))
        ev = result.job.event
        job = result.job
        ev.cause = models.Event.PUSH
        ev.save()
        step = job.recipe.steps.first()
        # if not a PULL_REQUEST, it should just return
        url = "foo"
        ProcessCommands.process_commands(url, job)
        self.assertEqual(mock_post.call_count, 0)
        self.assertEqual(mock_submodule.call_count, 0)

        ev.cause = models.Event.PULL_REQUEST
        ev.save()
        # No commands in the environment
        ProcessCommands.process_commands(url, job)
        self.assertEqual(mock_post.call_count, 0)
        self.assertEqual(mock_submodule.call_count, 0)

        utils.create_step_environment(name="CIVET_SERVER_POST_ON_SUBMODULE_UPDATE", value="1", step=step)
        ProcessCommands.process_commands(url, job)
        self.assertEqual(mock_post.call_count, 0)
        self.assertEqual(mock_submodule.call_count, 1)

        step.step_environment.all().delete()
        utils.create_step_environment(name="CIVET_SERVER_POST_COMMENT", value="1", step=step)
        ProcessCommands.process_commands(url, job)
        self.assertEqual(mock_post.call_count, 1)
        self.assertEqual(mock_submodule.call_count, 1)

        utils.create_step_environment(name="CIVET_SERVER_POST_REMOVE_OLD", value="1", step=step)
        ProcessCommands.process_commands(url, job)
        self.assertEqual(mock_post.call_count, 2)
        self.assertEqual(mock_submodule.call_count, 1)

        utils.create_step_environment(name="CIVET_SERVER_POST_EDIT_EXISTING", value="1", step=step)
        ProcessCommands.process_commands(url, job)
        self.assertEqual(mock_post.call_count, 3)
        self.assertEqual(mock_submodule.call_count, 1)

    @patch.object(OAuth2Session, 'post')
    @patch.object(OAuth2Session, 'get')
    @patch.object(OAuth2Session, 'delete')
    def test_process_commands_to_api(self, mock_del, mock_get, mock_post):
        """
        This should succeed down to the GitHub API level.
        """
        mock_del.return_value = utils.Response()
        mock_get.return_value = utils.Response()
        mock_post.return_value = utils.Response()

        update_key = "CIVET_CLIENT_SUBMODULE_UPDATES"
        post_key = "CIVET_CLIENT_POST_MESSAGE"
        result = self.create_step_result("PREVIOUS\n%s=libmesh\n%s=My message" % (update_key, post_key))
        ev = result.job.event
        job = result.job
        ev.cause = models.Event.PULL_REQUEST
        ev.comments_url = "some url"
        ev.save()
        step = job.recipe.steps.first()
        url = "foo"

        utils.create_step_environment(name="CIVET_SERVER_POST_ON_SUBMODULE_UPDATE", value="1", step=step)
        ProcessCommands.process_commands(url, job)

        step.step_environment.all().delete()
        utils.create_step_environment(name="CIVET_SERVER_POST_COMMENT", value="1", step=step)
        ProcessCommands.process_commands(url, job)

        utils.create_step_environment(name="CIVET_SERVER_POST_REMOVE_OLD", value="1", step=step)
        ProcessCommands.process_commands(url, job)

        utils.create_step_environment(name="CIVET_SERVER_POST_EDIT_EXISTING", value="1", step=step)
        ProcessCommands.process_commands(url, job)
