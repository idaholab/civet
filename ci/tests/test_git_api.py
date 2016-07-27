
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

from django.test import TestCase
from ci.git_api import GitAPI
class GitAPITestCase(TestCase):
  """
  this class is just a base class for the actual git servers.
  You can't even instantiate an instance since it has
  abstract methods.
  """
  def test_api(self):
    with self.assertRaises(Exception):
      gapi = GitAPI()
      gapi.sign_in_url()
      gapi.repo_url('owner', 'repo')
      gapi.commit_html_url('owner', 'repo', 'sha')
      gapi.get_repos('auth_session', 'session')
      gapi.get_branches('auth_session', 'owner', 'repo')
      gapi.update_pr_status('auth_session', 'base', 'head', 'state', 'event_url', 'desc', 'context')
      gapi.is_collaborator('auth_session', 'user', 'repo')
      gapi.pr_comment('auth_session', 'url', 'msg')
      gapi.last_sha('auth_session', 'owner', 'repo', 'branch')
      gapi.install_webhooks('request', 'auth_session', 'user', 'repo')
