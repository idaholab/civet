from django.contrib import admin
from . import models

class RecipeEnvironmentInline(admin.TabularInline):
  model = models.RecipeEnvironment
  extra = 1

class StepInline(admin.TabularInline):
  model = models.Step
  fields = ['name', 'position', 'filename']
  extra = 1

class PreStepSourceInline(admin.TabularInline):
  model = models.PreStepSource
  extra = 1

class StepResultInline(admin.TabularInline):
  model = models.StepResult
  extra = 0

class RecipeAdmin(admin.ModelAdmin):
  inlines = [
      RecipeEnvironmentInline,
      PreStepSourceInline,
      StepInline,
      ]
  search_fields = ['name', 'display_name', 'repository__name', 'repository__user__name']

admin.site.register(models.Recipe, RecipeAdmin)

class GitUserAdmin(admin.ModelAdmin):
  search_fields = ['name']

admin.site.register(models.GitUser, GitUserAdmin)

class OSVersionAdmin(admin.ModelAdmin):
  search_fields = ['name', 'version', 'other']

admin.site.register(models.OSVersion, OSVersionAdmin)

class LoadedModuleAdmin(admin.ModelAdmin):
  search_fields = ['name']

admin.site.register(models.LoadedModule, LoadedModuleAdmin)

class RepositoryAdmin(admin.ModelAdmin):
  search_fields = ['name', 'user__name']

admin.site.register(models.Repository, RepositoryAdmin)

class BranchAdmin(admin.ModelAdmin):
  search_fields = ['name', 'repository__name', 'repository__user__name']

admin.site.register(models.Branch, BranchAdmin)

class CommitAdmin(admin.ModelAdmin):
  search_fields = ['sha', 'branch__name', 'branch__repository__name', 'branch__repository__user__name']

admin.site.register(models.Commit, CommitAdmin)

class EventAdmin(admin.ModelAdmin):
  search_fields = ['build_user__name',
      'head__branch__name',
      'head__branch__repository__name',
      'head__branch__repository__user__name',
      'base__branch__name',
      'base__branch__repository__name',
      'base__branch__repository__user__name',
      'pull_request__title',
      'pull_request__number',
      ]
admin.site.register(models.Event, EventAdmin)

class PullRequestAdmin(admin.ModelAdmin):
  search_fields = ['title', 'number']

admin.site.register(models.PullRequest, PullRequestAdmin)

class JobAdmin(admin.ModelAdmin):
  inlines = [StepResultInline,]
  search_fields = ['recipe__name', 'config__name', 'recipe__repository__name']

admin.site.register(models.Job, JobAdmin)

class RecipeEnvironmentAdmin(admin.ModelAdmin):
  search_fields = ['recipe__name', 'name']

admin.site.register(models.RecipeEnvironment, RecipeEnvironmentAdmin)

class PreStepSourceAdmin(admin.ModelAdmin):
  search_fields = ['recipe__name', 'filename']

admin.site.register(models.PreStepSource, PreStepSourceAdmin)

class StepAdmin(admin.ModelAdmin):
  search_fields = ['recipe__name', 'name', 'filename']

admin.site.register(models.Step, StepAdmin)

class StepEnvironmentAdmin(admin.ModelAdmin):
  search_fields = ['step__recipe__name', 'step__name', 'name']

admin.site.register(models.StepEnvironment, StepEnvironmentAdmin)

class StepResultAdmin(admin.ModelAdmin):
  search_fields = ['step__recipe__name', 'step__name']
admin.site.register(models.StepResult, StepResultAdmin)

admin.site.register(models.Client)
admin.site.register(models.GitServer)
admin.site.register(models.BuildConfig)
