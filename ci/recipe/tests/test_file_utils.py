
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

class Tests(RecipeTester.RecipeTester):
  def test_is_subdir(self):
    base = self.recipes_dir
    common = os.path.join(self.recipes_dir, 'common')
    test = os.path.join(self.recipes_dir, 'test')
    p = os.path.join(common, 'foo', 'bar.sh')
    self.assertTrue(file_utils.is_subdir(p, base))
    self.assertTrue(file_utils.is_subdir(p, common))
    self.assertFalse(file_utils.is_subdir(p, test))

    p = os.path.join(common, '..', 'test', 'bar.sh')
    self.assertTrue(file_utils.is_subdir(p, base))
    self.assertFalse(file_utils.is_subdir(p, common))
    self.assertTrue(file_utils.is_subdir(p, test))

    p = os.path.join(common, '..', '..', 'test', 'bar.sh')
    self.assertFalse(file_utils.is_subdir(p, base))
    self.assertFalse(file_utils.is_subdir(p, common))
    self.assertFalse(file_utils.is_subdir(p, test))

  def test_get_contents(self):
    fname = "scripts/1.sh"
    self.write_script_to_repo("contents", "1.sh")
    ret = file_utils.get_contents(self.recipes_dir, fname)
    self.assertEqual(ret, 'contents')
    ret = file_utils.get_contents(self.recipes_dir, 'no_exist')
    self.assertEqual(ret, None)
    p = os.path.relpath('/etc/passwd', self.recipes_dir)
    ret = file_utils.get_contents(self.recipes_dir, p)
    self.assertEqual(ret, None)

  def test_is_valid_file(self):
    self.write_script_to_repo("contents", "1.sh")
    self.write_script_to_repo("contents", "2.sh")
    self.assertFalse(file_utils.is_valid_file(self.recipes_dir, "no_exist"))
    self.assertTrue(file_utils.is_valid_file(self.recipes_dir, "scripts/1.sh"))
    self.assertTrue(file_utils.is_valid_file(self.recipes_dir, "scripts/2.sh"))

    fname = os.path.join('..', '1.sh')
    self.assertFalse(file_utils.is_valid_file(self.recipes_dir, fname))
    if os.path.exists("/etc/passwd"):
      fname = os.path.join('..', '..', '..', 'etc', 'passwd')
      self.assertFalse(file_utils.is_valid_file(self.recipes_dir, fname))

  def test_get_repo_sha(self):
    sha = file_utils.get_repo_sha(self.recipes_dir)
    self.assertEqual(len(sha), 40)

    sha = file_utils.get_repo_sha("/tmp")
    self.assertEqual(sha, "")

  def test_get_file_sha(self):
    self.write_script_to_repo("contents", "1.sh")
    sha = file_utils.get_file_sha(self.recipes_dir, "scripts/1.sh")
    self.assertEqual(len(sha), 40)

    sha = file_utils.get_file_sha(self.recipes_dir, "noexist")
    self.assertEqual(sha, "")

    fname = os.path.join(self.recipes_dir, "noexist")
    with open(fname, "w") as f:
      f.write("noexist")

    sha = file_utils.get_file_sha(self.recipes_dir, "noexist")
    self.assertEqual(sha, "")
