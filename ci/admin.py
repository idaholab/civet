from django.contrib import admin
from django import forms
from . import models

class RecipeEnvironmentInline(admin.TabularInline):
  model = models.RecipeEnvironment
  extra = 1

class RecipeDependencyForm(forms.ModelForm):
  class Meta:
    model = models.RecipeDependency
    exclude = ['recipe']

class RecipeDependencyInline(admin.TabularInline):
  model = models.RecipeDependency
  form = RecipeDependencyForm
  extra = 1
  fk_name = 'recipe'


class StepInline(admin.TabularInline):
  model = models.Step
  fields = ['name', 'position', 'filename']
  extra = 1

class PreStepSourceInline(admin.TabularInline):
  model = models.PreStepSource
  extra = 1

class RecipeAdmin(admin.ModelAdmin):
  inlines = [
      RecipeDependencyInline,
      RecipeEnvironmentInline,
      PreStepSourceInline,
      StepInline,
      ]

admin.site.register(models.Recipe, RecipeAdmin)

admin.site.register(models.GitUser)
admin.site.register(models.Repository)
admin.site.register(models.Branch)
admin.site.register(models.Commit)
admin.site.register(models.Event)
admin.site.register(models.PullRequest)
admin.site.register(models.BuildConfig)
admin.site.register(models.RecipeEnvironment)
admin.site.register(models.PreStepSource)
admin.site.register(models.Step)
admin.site.register(models.StepEnvironment)
admin.site.register(models.Client)
admin.site.register(models.Job)
admin.site.register(models.StepResult)
admin.site.register(models.GitServer)
admin.site.register(models.OAuthToken)
