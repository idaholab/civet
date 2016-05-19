from ci.recipe import file_utils
import utils
import os

class FileUtilsTests(utils.RecipeTestCase):
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
