from django.test import TestCase
from django.conf import settings
import shutil
from ci.tests import utils
from ci.recipe import forms
from os import path

class FormsTestCase(TestCase):
  fixtures = ['base']

  def setUp(self):
    self.recipe_dir, self.repo = utils.create_recipe_dir()
    settings.RECIPE_BASE_DIR = self.recipe_dir

  def tearDown(self):
    shutil.rmtree(self.recipe_dir)

  def test_filenamewidget(self):
    widget = forms.FilenameWidget(user=None)
    self.assertEqual(widget._username, '')
    # choices should only be new file
    self.assertEqual(len(widget.choices()), 1)
    user = utils.get_test_user()
    widget = forms.FilenameWidget(user=user)
    self.assertGreater(len(widget.choices()), 1)
    vals = widget.decompress(path.join('common', '1.sh'))
    self.assertEqual(vals[0], path.join('common', '1.sh'))
    self.assertEqual(vals[1], path.join('common', '1.sh'))
    self.assertEqual(vals[2], '1.sh')

  def test_step_formset(self):
    user = utils.get_test_user()
    forms.create_step_nestedformset(user=user)
    forms.create_prestep_formset(user=user)
    forms.DependencyFormset()
    forms.create_env_formset()
