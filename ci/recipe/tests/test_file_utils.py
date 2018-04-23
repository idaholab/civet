
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
from ci.recipe import file_utils
import RecipeTester
from ci.tests import utils
import os

class Tests(RecipeTester.RecipeTester):
    def test_is_subdir(self):
        with utils.RecipeDir() as recipes_dir:
            base = recipes_dir
            common = os.path.join(recipes_dir, 'common')
            test = os.path.join(recipes_dir, 'test')
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
        with utils.RecipeDir() as recipes_dir:
            fname = "scripts/1.sh"
            self.write_script_to_repo(recipes_dir, "contents", "1.sh")
            ret = file_utils.get_contents(recipes_dir, fname)
            self.assertEqual(ret, 'contents')
            ret = file_utils.get_contents(recipes_dir, 'no_exist')
            self.assertEqual(ret, None)
            p = os.path.relpath('/etc/passwd', recipes_dir)
            ret = file_utils.get_contents(recipes_dir, p)
            self.assertEqual(ret, None)

    def test_is_valid_file(self):
        with utils.RecipeDir() as recipes_dir:
            self.write_script_to_repo(recipes_dir, "contents", "1.sh")
            self.write_script_to_repo(recipes_dir, "contents", "2.sh")
            self.assertFalse(file_utils.is_valid_file(recipes_dir, "no_exist"))
            self.assertTrue(file_utils.is_valid_file(recipes_dir, "scripts/1.sh"))
            self.assertTrue(file_utils.is_valid_file(recipes_dir, "scripts/2.sh"))

            fname = os.path.join('..', '1.sh')
            self.assertFalse(file_utils.is_valid_file(recipes_dir, fname))
            if os.path.exists("/etc/passwd"):
                fname = os.path.join('..', '..', '..', 'etc', 'passwd')
                self.assertFalse(file_utils.is_valid_file(recipes_dir, fname))

    def test_get_repo_sha(self):
        with utils.RecipeDir() as recipes_dir:
            sha = file_utils.get_repo_sha(recipes_dir)
            self.assertEqual(len(sha), 40)

            sha = file_utils.get_repo_sha("/tmp")
            self.assertEqual(sha, "")

    def test_get_file_sha(self):
        with utils.RecipeDir() as recipes_dir:
            self.write_script_to_repo(recipes_dir, "contents", "1.sh")
            sha = file_utils.get_file_sha(recipes_dir, "scripts/1.sh")
            self.assertEqual(len(sha), 40)

            sha = file_utils.get_file_sha(recipes_dir, "noexist")
            self.assertEqual(sha, "")

            fname = os.path.join(recipes_dir, "noexist")
            with open(fname, "w") as f:
                f.write("noexist")

            sha = file_utils.get_file_sha("/tmp/noexist", "noexist")
            self.assertEqual(sha, "")
