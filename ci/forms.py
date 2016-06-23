from django import forms
from ci import models

class JobInfoForm(forms.Form):
  os_versions = forms.ModelMultipleChoiceField(
      queryset=models.OSVersion.objects.order_by("name", "version"),
      widget=forms.CheckboxSelectMultiple,
      required=False)
  modules = forms.ModelMultipleChoiceField(
      queryset=models.LoadedModule.objects.order_by("name"),
      widget=forms.CheckboxSelectMultiple,
      required=False)

class AlternateRecipesForm(forms.Form):
  recipes = forms.MultipleChoiceField(widget=forms.CheckboxSelectMultiple, required=False)

class UserRepositorySettingsForm(forms.Form):
  repositories = forms.MultipleChoiceField(widget=forms.CheckboxSelectMultiple, required=False)
