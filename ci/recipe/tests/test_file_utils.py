from django.test import TestCase
from django.core import exceptions
from ci.recipe import file_utils
from ci.tests import utils
import shutil
from os import path

class FileUtilsTestCase(TestCase):
  fixtures = ['base']

  def setUp(self):
    self.recipe_dir, self.repo = utils.create_recipe_dir()

  def tearDown(self):
    shutil.rmtree(self.recipe_dir)

  def check_file_dict(self, file_dict, subdir):
    self.assertIn(subdir, file_dict)
    self.assertIn(path.join(subdir, '1.sh'), file_dict[subdir])
    self.assertIn(path.join(subdir, '2.sh'), file_dict[subdir])

  def test_get_file_dict(self):
    files = file_utils.get_file_dict(self.recipe_dir, 'common')
    self.check_file_dict(files, 'common')
    self.check_file_dict(files, path.join('common', 'subdir0'))
    self.check_file_dict(files, path.join('common', 'subdir1'))

    files = file_utils.get_file_dict(self.recipe_dir, 'test')
    self.check_file_dict(files, 'test')
    self.check_file_dict(files, path.join('test', 'subdir0'))
    self.check_file_dict(files, path.join('test', 'subdir1'))

  def test_get_filename_in_db(self):
    # valid file
    p = file_utils.get_filename_in_db(self.recipe_dir, 'test', path.join('test', '1.sh'))
    self.assertEqual(p, path.join('test', '1.sh'))

    # file that doesn't start with the username
    p = file_utils.get_filename_in_db(self.recipe_dir, 'test', path.join('other', '1.sh'))
    self.assertEqual(p, path.join('test', 'other', '1.sh'))

    # common file
    p = file_utils.get_filename_in_db(self.recipe_dir, 'test', path.join('common', '1.sh'))
    self.assertEqual(p, path.join('common', '1.sh'))

    # invalid filename
    p = file_utils.get_filename_in_db(self.recipe_dir, 'test', path.join('..', '1.sh'))
    self.assertEqual(p, None)

  def test_to_choices(self):
    files = file_utils.get_file_dict(self.recipe_dir, 'common')
    self.assertEqual(len(files), 3)
    choices = file_utils.to_choices(files)
    # should be the 3 directories
    self.assertEqual(len(choices), 3)
    # should be a tuple
    self.assertEqual(len(choices[0]), 2)
    # should be the directory name
    self.assertEqual(choices[0][0], 'common')
    # should be the two file tuples
    self.assertEqual(len(choices[0][1]), 2)
    # should be the relative path to the first file
    self.assertEqual(choices[0][1][0][0], path.join('common', '1.sh'))
    # should be the filename of the first file
    self.assertEqual(choices[0][1][0][1], '1.sh')
    # should be the second directory
    self.assertEqual(choices[1][0], path.join('common', 'subdir0'))
    self.assertEqual(len(choices[1][1]), 2)
    # should be the third directory
    self.assertEqual(choices[2][0], path.join('common', 'subdir1'))
    self.assertEqual(len(choices[2][1]), 2)

  def test_get_all_choices(self):
    all_choices = file_utils.get_all_choices(self.recipe_dir, 'test')
    # should be 3 directories each for 'test' and 'common'
    # plus a 'New File' choice
    self.assertEqual(len(all_choices), 7)
    for idx in xrange(1,7):
      self.assertEqual(len(all_choices[idx]), 2)
      self.assertEqual(len(all_choices[idx]), 2)

  def test_is_subdir(self):
    base = self.recipe_dir
    common = path.join(self.recipe_dir, 'common')
    test = path.join(self.recipe_dir, 'test')
    p = path.join(common, 'foo', 'bar.sh')
    self.assertTrue(file_utils.is_subdir(p, base))
    self.assertTrue(file_utils.is_subdir(p, common))
    self.assertFalse(file_utils.is_subdir(p, test))

    p = path.join(common, '..', 'test', 'bar.sh')
    self.assertTrue(file_utils.is_subdir(p, base))
    self.assertFalse(file_utils.is_subdir(p, common))
    self.assertTrue(file_utils.is_subdir(p, test))

    p = path.join(common, '..', '..', 'test', 'bar.sh')
    self.assertFalse(file_utils.is_subdir(p, base))
    self.assertFalse(file_utils.is_subdir(p, common))
    self.assertFalse(file_utils.is_subdir(p, test))

  def test_get_contents(self):
    fname = path.join('common', '1.sh')
    ret = file_utils.get_contents(self.recipe_dir, fname)
    self.assertEqual(ret, '1.sh')
    ret = file_utils.get_contents(self.recipe_dir, 'no_exist')
    self.assertEqual(ret, None)
    p = path.relpath('/etc/passwd', self.recipe_dir)
    ret = file_utils.get_contents(self.recipe_dir, p)
    self.assertEqual(ret, None)

  def test_get_versions(self):
    base = self.recipe_dir
    p = path.join('test', '1.sh')
    versions = file_utils.get_versions(base, p)
    self.assertEqual(len(versions), 1)
    self.assertNotEqual(versions[0][0], None)
    self.assertNotEqual(versions[0][1], None)
    p = path.join('test', 'no_exist')
    versions = file_utils.get_versions(base, p)
    self.assertEqual(len(versions), 0)

  def test_get_version(self):
    p = path.join('test', '1.sh')
    ret = file_utils.get_versions(self.recipe_dir, p)
    self.assertEqual(len(ret), 1)
    version = file_utils.get_version(self.recipe_dir, p, ret[0][0])
    self.assertEqual(version, '1.sh')
    version = file_utils.get_version(self.recipe_dir, p, '123')
    self.assertEqual(version, None)

    p = path.join('test', 'no_exist')
    version = file_utils.get_version(self.recipe_dir, p, '123')
    self.assertEqual(version, None)


  def test_is_valid_file(self):
    fname = path.join('test', 'subdir0', '1.sh')
    self.assertTrue(file_utils.is_valid_file(self.recipe_dir, 'test', fname))
    self.assertFalse(file_utils.is_valid_file(self.recipe_dir, 'no_user', fname))

    fname = path.join('test', '..', 'subdir0', '1.sh')
    self.assertFalse(file_utils.is_valid_file(self.recipe_dir, 'test', fname))
    self.assertTrue(file_utils.is_valid_file(self.recipe_dir, 'subdir0', fname))

  def test_check_save(self):
    #invalid file name
    p = path.join('test', '..', '1.sh')
    with self.assertRaises(exceptions.SuspiciousOperation):
      file_utils.check_save(self.recipe_dir, 'test', p)

    # can't save common files
    p = path.join('common', '1.sh')
    with self.assertRaises(exceptions.PermissionDenied):
      file_utils.check_save(self.recipe_dir, 'test', p)

    # can't make a directory where a file already is
    p = path.join('test', '1.sh', 'other_file')
    with self.assertRaises(exceptions.PermissionDenied):
      file_utils.check_save(self.recipe_dir, 'test', p)

  def test_commit_file(self):
    # existing file
    p = path.join('test', '1.sh')
    versions_before = file_utils.get_versions(self.recipe_dir, p)
    file_utils.commit_file(self.recipe_dir, 'test', p, 'new contents', False)
    versions_after = file_utils.get_versions(self.recipe_dir, p)
    self.assertEqual(len(versions_before)+1, len(versions_after))
    contents = file_utils.get_contents(self.recipe_dir, p )
    self.assertEqual(contents, 'new contents')

    # new file
    p = path.join('test', 'new_file.sh')
    versions_before = file_utils.get_versions(self.recipe_dir, p)
    file_utils.commit_file(self.recipe_dir, 'test', p, 'new contents', True)
    versions_after = file_utils.get_versions(self.recipe_dir, p)
    self.assertEqual(len(versions_before)+1, len(versions_after))
    contents = file_utils.get_contents(self.recipe_dir, p )
    self.assertEqual(contents, 'new contents')

    # write error
    p = path.join('test', 'subdir0')
    with self.assertRaises(exceptions.PermissionDenied):
      file_utils.commit_file(self.recipe_dir, 'test', p, 'new contents', False)

  def test_save_file(self):
    # existing file
    p = path.join('test', '1.sh')
    versions_before = file_utils.get_versions(self.recipe_dir, p)
    file_utils.save_file(self.recipe_dir, 'test', p, 'new contents')
    versions_after = file_utils.get_versions(self.recipe_dir, p)
    self.assertEqual(len(versions_before)+1, len(versions_after))
    contents = file_utils.get_contents(self.recipe_dir, p )
    self.assertEqual(contents, 'new contents')

    # new file
    p = path.join('test', 'other_subdir', 'another_subdir', '1.sh')
    versions_before = file_utils.get_versions(self.recipe_dir, p)
    file_utils.save_file(self.recipe_dir, 'test', p, 'new contents')
    versions_after = file_utils.get_versions(self.recipe_dir, p)
    self.assertEqual(len(versions_before)+1, len(versions_after))
    contents = file_utils.get_contents(self.recipe_dir, p )
    self.assertEqual(contents, 'new contents')
