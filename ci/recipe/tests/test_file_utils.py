
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

from ci.recipe import file_utils
import RecipeTester
import os

class FileUtilsTests(RecipeTester.RecipeTester):
  def test_get_repo_sha(self):
    sha = file_utils.get_repo_sha(self.repo_dir)
    self.assertEqual(len(sha), 40)

    sha = file_utils.get_repo_sha("/tmp")
    self.assertEqual(sha, "")

  def test_get_contents(self):
    self.write_script_to_repo("contents", "1.sh")
    fname = os.path.join('scripts', '1.sh')
    ret = file_utils.get_contents(self.repo_dir, fname)
    self.assertEqual(ret, 'contents')
    ret = file_utils.get_contents(self.repo_dir, 'no_exist')
    self.assertEqual(ret, None)
