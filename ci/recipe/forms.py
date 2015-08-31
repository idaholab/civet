from django.forms import ModelForm
from django import forms
from django.forms.models import inlineformset_factory, BaseInlineFormSet
from django.utils.safestring import mark_safe
from nested_formset import nestedformset_factory, BaseNestedFormset
from ci import models
from ci.recipe import file_utils
from django.conf import settings
import logging
logger = logging.getLogger('ci')

class FilenameWidget(forms.MultiWidget):
  def __init__(self, user, attrs=None):
    self._base_dir = settings.RECIPE_BASE_DIR
    self._username = ''
    select_attrs = {'class': 'filename_select'}
    if user:
      select_attrs['onchange'] = 'changeContents(this, "{}")'.format(user.name)
      self._username = user.name
    _widgets = (
        forms.TextInput(),
        forms.widgets.Select(attrs=select_attrs, choices=self.choices()),
        forms.Textarea(attrs={'cols':80, 'rows': '20'}),
          )
    super(FilenameWidget, self).__init__(_widgets, attrs)

  def choices(self):
    if self._username:
      choices = file_utils.get_all_choices(self._base_dir, self._username)
    else:
      choices = [(None, 'New file'),]
    return choices

  def render(self, name, value, attrs=None):
    self.prefix = name
    return super(FilenameWidget, self).render(name, value, attrs)

  def format_output(self, rendered_widgets):
    return mark_safe('<td>{}</td><td>{}</td><td>{}</td>'.format(rendered_widgets[0], rendered_widgets[1], rendered_widgets[2]))

  def decompress(self, value):
    """
    This takes a single value from the database and we need
    to generate the values for each of the widgets
    """
    if value:
      # the first is for the filename, second is for select box, third is file contents
      vals = [value, value, file_utils.get_contents(self._base_dir, value)]
      return vals
    return [None, None, None]

  def value_from_datadict(self, data, files, name):
    self._values = [ w.value_from_datadict(data, files, '{}_{}'.format(name, i)) for i, w in enumerate(self.widgets)]
    if not self._values[0]:
      return ''
    return file_utils.get_filename_in_db(self._base_dir, self._username, self._values[0])

  def values(self):
    return self._values

  def is_valid(self):
    if self._values[0]:
      return file_utils.is_valid_file(self._base_dir, self._username, self._values[0])
    return False

  def save_to_disk(self):
    """
    Save the file to disk.
    Will only save if there is a filename set.
    """
    if self._values[0]:
      file_utils.save_file(self._base_dir, self._username, self._values[0], self._values[2])

class FilenameNestedFormset(BaseNestedFormset):
  def clean(self):
    super(FilenameNestedFormset, self).clean()
    for form in self.forms:
      filename = form.fields['filename']
      fname = form.cleaned_data.get('filename')
      if fname and not filename.widget.is_valid():
        form.add_error('filename', 'Invalid filename')

class FilenameInlineFormset(BaseInlineFormSet):
  def clean(self):
    super(FilenameInlineFormset, self).clean()
    for form in self.forms:
      filename = form.fields['filename']
      fname = form.cleaned_data.get('filename')
      if fname and not filename.widget.is_valid():
        form.add_error('filename', 'Invalid filename')


def create_step_nestedformset(user, data=None, instance=None):
  factory = nestedformset_factory(
      models.Recipe,
      models.Step,
      nested_formset=inlineformset_factory(
        models.Step,
        models.StepEnvironment,
        fields=('name', 'value',),
        can_delete=True,
        extra=1
        ),
      fields=('name', 'filename'),
      formset=FilenameNestedFormset,
      widgets={'filename': FilenameWidget(user)},
      can_delete=True,
      extra=1)
  return factory(data, instance=instance)


DependencyFormset = inlineformset_factory(
  models.Recipe,
  models.RecipeDependency,
  fk_name='recipe',
  fields=('dependency', 'abort_on_failure'),
  extra=1,
  )

EnvFormset = inlineformset_factory(
    models.Recipe,
    models.RecipeEnvironment,
    fields=('name', 'value'),
    can_delete=True,
    extra=1,
    )

def create_prestep_formset(user, data=None, instance=None):
  factory = inlineformset_factory(
      models.Recipe,
      models.PreStepSource,
      fields=('filename',),
      widgets={'filename': FilenameWidget(user)},
      formset=FilenameInlineFormset,
      can_delete=True,
      extra=1,
      )
  return factory(data, instance=instance)

class RecipeForm(ModelForm):
  class Meta:
    model = models.Recipe
    exclude = ['last_modified', 'created', 'dependencies']
    widgets = {'creator': forms.HiddenInput(),
      'repository': forms.HiddenInput(),
      }
    help_texts = {
        'active': 'This is some help text for active',
        }

  def clean(self):
    cleaned_data = super(RecipeForm, self).clean()
    branch = cleaned_data.get('branch')
    cause = cleaned_data.get('cause')
    if cause != models.Recipe.CAUSE_PULL_REQUEST and not branch:
      self.add_error('branch', 'Branch required on this type of trigger')
