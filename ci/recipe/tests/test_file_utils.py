from ci.recipe import file_utils
import os
import utils

class FileUtilsTests(utils.RecipeTestCase):
  def test_is_subdir(self):
    base = self.repo_dir
    common = os.path.join(self.repo_dir, 'common')
    test = os.path.join(self.repo_dir, 'test')
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
    fname = os.path.join('scripts', '1.sh')
    ret = file_utils.get_contents(self.repo_dir, fname)
    self.assertEqual(ret, '1.sh')
    ret = file_utils.get_contents(self.repo_dir, 'no_exist')
    self.assertEqual(ret, None)
    p = os.path.relpath('/etc/passwd', self.repo_dir)
    ret = file_utils.get_contents(self.repo_dir, p)
    self.assertEqual(ret, None)

  def test_is_valid_file(self):
    self.assertFalse(file_utils.is_valid_file(self.repo_dir, "no_exist"))
    self.assertTrue(file_utils.is_valid_file(self.repo_dir, "scripts/1.sh"))
    fname = os.path.join('scripts/subdir0', '1.sh')
    self.assertTrue(file_utils.is_valid_file(self.repo_dir, fname))

    fname = os.path.join('..', '1.sh')
    self.assertFalse(file_utils.is_valid_file(self.repo_dir, fname))
    if os.path.exists("/etc/passwd"):
      fname = os.path.join('..', '..', '..', 'etc', 'passwd')
      self.assertFalse(file_utils.is_valid_file(self.repo_dir, fname))

  def test_get_repo_sha(self):
    sha = file_utils.get_repo_sha(self.repo_dir)
    self.assertEqual(len(sha), 40)

    sha = file_utils.get_repo_sha("/tmp")
    self.assertEqual(sha, "")

  def test_get_file_sha(self):
    sha = file_utils.get_file_sha(self.repo_dir, "scripts/1.sh")
    self.assertEqual(len(sha), 40)

    sha = file_utils.get_file_sha(self.repo_dir, "noexist")
    self.assertEqual(sha, "")

    fname = os.path.join(self.repo_dir, "noexist")
    with open(fname, "w") as f:
      f.write("noexist")

    sha = file_utils.get_file_sha(self.repo_dir, "noexist")
    self.assertEqual(sha, "")
