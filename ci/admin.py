
# Copyright 2016-2025 Battelle Energy Alliance, LLC
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

from __future__ import unicode_literals, absolute_import
from django.contrib import admin
from . import models

class RecipeEnvironmentInline(admin.TabularInline):
    model = models.RecipeEnvironment
    readonly_fields =  ['name', 'value']
    can_delete = False
    max_num = 0

class StepInline(admin.TabularInline):
    model = models.Step
    readonly_fields = ['name', 'position', 'filename', 'abort_on_failure', 'allowed_to_fail']
    can_delete = False
    max_num = 0

class PreStepSourceInline(admin.TabularInline):
    model = models.PreStepSource
    readonly_fields = ['filename']
    can_delete = False
    max_num = 0

@admin.register(models.Recipe)
class RecipeAdmin(admin.ModelAdmin):
    inlines = [
        RecipeEnvironmentInline,
        PreStepSourceInline,
        StepInline,
        ]
    search_fields = ['filename', 'name', 'display_name', 'repository__name', 'repository__user__name']
    list_display = ['recipe_display']
    def recipe_display(self, obj):
        return "%s : %s" % (obj.filename, obj.cause_str())

@admin.register(models.GitUser)
class GitUserAdmin(admin.ModelAdmin):
    search_fields = ['name']

@admin.register(models.OSVersion)
class OSVersionAdmin(admin.ModelAdmin):
    search_fields = ['name', 'version', 'other']

@admin.register(models.LoadedModule)
class LoadedModuleAdmin(admin.ModelAdmin):
    search_fields = ['name']

@admin.register(models.Repository)
class RepositoryAdmin(admin.ModelAdmin):
    search_fields = ['name', 'user__name']

@admin.register(models.Branch)
class BranchAdmin(admin.ModelAdmin):
    search_fields = ['name', 'repository__name', 'repository__user__name']

@admin.register(models.Commit)
class CommitAdmin(admin.ModelAdmin):
    search_fields = ['sha', 'branch__name', 'branch__repository__name', 'branch__repository__user__name']

@admin.register(models.Event)
class EventAdmin(admin.ModelAdmin):
    search_fields = ['build_user__name',
        'head__sha',
        'head__branch__name',
        'head__branch__repository__name',
        'head__branch__repository__user__name',
        'base__sha',
        'base__branch__name',
        'base__branch__repository__name',
        'base__branch__repository__user__name',
        'pull_request__title',
        'pull_request__number',
        'id',
        ]
    readonly_fields = ['json_data', 'comments_url']

@admin.register(models.PullRequest)
class PullRequestAdmin(admin.ModelAdmin):
    search_fields = ['title', 'number']

class StepResultInline(admin.TabularInline):
    model = models.StepResult
    exclude = ['output', 'position']
    readonly_fields = ['name', 'filename', 'abort_on_failure', 'allowed_to_fail', 'seconds', 'exit_status']
    can_delete = False
    max_num = 0

@admin.register(models.Job)
class JobAdmin(admin.ModelAdmin):
    inlines = [StepResultInline,]
    search_fields = ['recipe__name', 'config__name', 'recipe__repository__name', 'id']

@admin.register(models.RecipeEnvironment)
class RecipeEnvironmentAdmin(admin.ModelAdmin):
    search_fields = ['recipe__name', 'recipe__filname', 'name']
    list_display = ['env_display']
    readonly_fields = ['recipe']

    def env_display(self, obj):
        return "%s : %s=%s" % (obj.recipe.filename, obj.name, obj.value)

@admin.register(models.PreStepSource)
class PreStepSourceAdmin(admin.ModelAdmin):
    search_fields = ['recipe__name', 'recipe__filename', 'filename']
    list_display = ['prestep_display']

    def prestep_display(self, obj):
        return "%s : %s: %s" % (obj.recipe.filename, obj.recipe.cause_str(), obj.filename)

@admin.register(models.Step)
class StepAdmin(admin.ModelAdmin):
    search_fields = ['recipe__filename', 'name', 'filename']
    list_display = ['step_display']
    def step_display(self, obj):
        return "%s : %s : %s" % (obj.recipe.filename, obj.name, obj.filename)

@admin.register(models.StepEnvironment)
class StepEnvironmentAdmin(admin.ModelAdmin):
    search_fields = ['step__recipe__name', 'step__recipe__filname', 'name', 'value']
    list_display = ['env_display']
    readonly_fields = ['step']

    def env_display(self, obj):
        return "%s : %s: %s=%s" % (obj.step.recipe.filename, obj.step.name, obj.name, obj.value)
    search_fields = ['step__recipe__name', 'step__name', 'name']

@admin.register(models.StepResult)
class StepResultAdmin(admin.ModelAdmin):
    search_fields = ['filename', 'name']
    list_display = ['result_display']
    readonly_fields = ['output']

    def result_display(self, obj):
        return "%s: %s : %s" % (obj.job.recipe.filename, obj.job.pk, obj.name)

admin.site.register(models.Client)
admin.site.register(models.GitServer)
admin.site.register(models.BuildConfig)
