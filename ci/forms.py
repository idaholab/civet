
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
    default_recipes = forms.MultipleChoiceField(widget=forms.CheckboxSelectMultiple, required=False)

class UserRepositorySettingsForm(forms.Form):
    repositories = forms.MultipleChoiceField(widget=forms.CheckboxSelectMultiple, required=False)

class BranchEventsForm(forms.Form):
    filter_events = forms.MultipleChoiceField(choices=models.Event.CAUSE_CHOICES,
            widget=forms.CheckboxSelectMultiple,
            required=False)
    do_filter = forms.CharField(widget=forms.HiddenInput(), initial="1")
