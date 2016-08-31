
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
from ci.client import ProcessCommands
from ci.tests import utils
from ci import models

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

  def test_check_submodule_update(self):
    result = self.create_step_result("PREVIOUS_LINE\nCIVET_CLIENT_SUBMODULE_UPDATES=1\nNEXT_LINE\n")
    self.assertEqual(ProcessCommands.check_submodule_update(result.job, result.position), True)

  def test_check_post_comment(self):
    result = self.create_step_result("PREVIOUS_LINE\nCIVET_CLIENT_POST_MESSAGE=My message\n")
    self.assertEqual(ProcessCommands.check_post_comment(result.job, result.position), True)

  def test_process_commands(self):
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
    ProcessCommands.process_commands(job)

    ev.cause = models.Event.PULL_REQUEST
    ev.save()
    ProcessCommands.process_commands(job)

    utils.create_step_environment(name="CIVET_SERVER_POST_ON_SUBMODULE_UPDATE", value="1", step=step)
    ProcessCommands.process_commands(job)
    result.output = ""
    result.save()
    ProcessCommands.process_commands(job)
    result.output = "%s=" % update_key
    result.save()
    ProcessCommands.process_commands(job)
    ev.pull_request.review_comments_url = None
    ev.pull_request.save()
    result.output = "%s=libmesh" % update_key
    result.save()
    ProcessCommands.process_commands(job)

    step.step_environment.all().delete()
    utils.create_step_environment(name="CIVET_SERVER_POST_COMMENT", value="1", step=step)
    ProcessCommands.process_commands(job)
