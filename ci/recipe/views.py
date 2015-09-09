from django.shortcuts import redirect, get_object_or_404, render
from django.core.urlresolvers import reverse
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.views.generic import CreateView, DeleteView, UpdateView
from django.conf import settings
from ci import models
import os
from ci.recipe import forms
from django.contrib import messages

import logging
logger = logging.getLogger('ci')

def check_permission(request, user, repo):
  signed_in = repo.user.server.auth().signed_in_user(repo.user.server, request.session)
  if signed_in != user or not signed_in:
    raise PermissionDenied("You are not the owner of this recipe")

  auth_session = repo.user.server.auth().start_session_for_user(signed_in)
  if not repo.user.server.api().is_collaborator(auth_session, signed_in, repo):
    raise PermissionDenied("Signed in user is not a collaborator on this repo")

class RecipeBaseView(object):
  def create_branches(self, user, repo):
    auth_session = repo.user.server.auth().start_session_for_user(user)
    branches = repo.user.server.api().get_branches(
      auth_session,
      repo.user.name,
      repo.name,
      )
    for branch in branches:
      b, created = models.Branch.objects.get_or_create(name=branch, repository=repo)

  def get_context(self, creator, repo, form, env_forms, depend_forms, prestep_forms, step_forms):
    form.fields['branch'].queryset = models.Branch.objects.filter(repository=repo)
    queryset = models.Recipe.objects.filter(creator=creator, repository=repo).order_by('name')
    form.fields['auto_authorized'].queryset = models.GitUser.objects.filter(server__host_type=creator.server.host_type).order_by('name')
    if depend_forms.instance:
      queryset = queryset.exclude(pk=depend_forms.instance.pk)
    for depend in depend_forms:
      depend.fields['dependency'].queryset = queryset
    return self.render_to_response(
      self.get_context_data(
        creator=creator,
        repo=repo,
        form=form,
        env_forms=env_forms,
        depend_forms=depend_forms,
        prestep_forms=prestep_forms,
        step_forms=step_forms,
        ))

  def save_steps(self, step_forms):
    idx = 0
    for step in step_forms.forms:
      if step.cleaned_data.get('filename', None) and step.cleaned_data.get('name', None):
        step.cleaned_data['position'] = idx
        step.instance.position = idx
        step.instance.recipe = self.object
        idx = idx + 1
        step.fields['filename'].widget.save_to_disk()
        step.save()
        for nested in step.nested.forms:
          if nested.cleaned_data.get('name', None):
            if nested.instance.pk and nested.cleaned_data.get('DELETE'):
              nested.instance.delete()
            else:
              nested.instance.step = step.instance
              nested.save()
    step_forms.save()

class RecipeCreateView(RecipeBaseView, CreateView):
  template_name = 'ci/recipe_add.html'
  model = models.Recipe
  form_class = forms.RecipeForm

  def get(self, request, *args, **kwargs):
    if 'user_id' not in request.GET:
      raise Http404("User id is required.")
    if 'repo' not in request.GET:
      raise Http404("Repo is required.")

    creator = get_object_or_404(models.GitUser, pk=request.GET['user_id'])
    full_repo = request.GET['repo']
    owner, repo = full_repo.split('/')
    owner, created = models.GitUser.objects.get_or_create(name=owner, server=creator.server)
    repo, created = models.Repository.objects.get_or_create(name=repo, user=owner)
    self.create_branches(creator, repo)

    check_permission(self.request, creator, repo)
    self.object = None
    form_class = self.get_form_class()
    form = self.get_form(form_class)
    env_forms = forms.EnvFormset()
    depend_forms = forms.DependencyFormset()
    prestep_forms = forms.create_prestep_formset(creator)
    step_forms = forms.create_step_nestedformset(creator)
    return self.get_context(creator, repo, form, env_forms, depend_forms, prestep_forms, step_forms)


  def post(self, request, *args, **kwargs):
    user = get_object_or_404(models.GitUser, pk=request.POST['creator'])
    repo = get_object_or_404(models.Repository, pk=request.POST['repository'])
    check_permission(self.request, user, repo)
    self.object = None
    form_class = self.get_form_class()
    form = self.get_form(form_class)
    env_forms = forms.EnvFormset(self.request.POST)
    depend_forms = forms.DependencyFormset(self.request.POST)
    prestep_forms = forms.create_prestep_formset(user, self.request.POST)
    step_forms = forms.create_step_nestedformset(user, self.request.POST)

    valid = form.is_valid() and env_forms.is_valid()
    valid = valid and depend_forms.is_valid() and prestep_forms.is_valid()
    valid = valid and step_forms.is_valid()
    for step in step_forms.forms:
      valid = valid and step.nested.is_valid()
    if valid:
      return self.form_valid(form, env_forms, depend_forms, prestep_forms, step_forms, user, repo)
    else:
      logger.debug('Form:%s, env: %s, depend: %s, prestep: %s, step: %s' %
          (form.is_valid(), env_forms.is_valid(), depend_forms.is_valid(), prestep_forms.is_valid(), step_forms.is_valid()))
      return self.form_invalid(form, env_forms, depend_forms, prestep_forms, step_forms, user, repo)

  def form_valid(self, form, env_forms, depend_forms, prestep_forms, step_forms, user, repo):
    form.cleaned_data['creator_id'] = user.pk
    form.cleaned_data['repository_id'] = repo.pk
    self.object = form.save()
    env_forms.instance = self.object
    env_forms.save()
    depend_forms.instance = self.object
    depend_forms.save()
    prestep_forms.instance = self.object
    prestep_forms.save()
    step_forms.instance = self.object
    step_forms.instance.save()
    for f in prestep_forms:
      f.fields['filename'].widget.save_to_disk()

    self.save_steps(step_forms)
    messages.info(self.request, 'Saved recipe: %s ' % self.object.name )
    try:
      auth_session = user.server.auth().start_session(self.request.session)
      user.server.api().install_webhooks(self.request, auth_session, user, repo)
    except Exception as e:
      messages.warning(self.request, "Failed to install webhook. Error: %s" % e)
    return redirect('ci:view_profile', server_type=user.server.host_type)

  def form_invalid(self, form, env_forms, depend_forms, prestep_forms, step_forms, creator, repo):
    messages.error(self.request, 'Failed to save recipe. Please check for errors.')
    return self.get_context(creator, repo, form, env_forms, depend_forms, prestep_forms, step_forms)


class RecipeUpdateView(RecipeBaseView, UpdateView):
  template_name = 'ci/recipe_add.html'
  model = models.Recipe
  form_class = forms.RecipeForm

  def get(self, request, *args, **kwargs):
    self.object = self.get_object()
    check_permission(self.request, self.object.creator, self.object.repository)
    form_class = self.get_form_class()
    form = self.get_form(form_class)
    self.create_branches(self.object.creator, self.object.repository)
    form.fields['branch'].queryset = models.Branch.objects.filter(repository=self.object.repository).all()
    form.fields['auto_authorized'].queryset = models.GitUser.objects.filter(server__host_type=self.object.creator.server.host_type).order_by('name')
    env_forms = forms.EnvFormset(instance=self.object)
    depend_forms = forms.DependencyFormset(instance=self.object)
    prestep_forms = forms.create_prestep_formset(self.object.creator, instance=self.object)
    step_forms = forms.create_step_nestedformset(self.object.creator, instance=self.object)
    return self.get_context(self.object.creator, self.object.repository, form, env_forms, depend_forms, prestep_forms, step_forms)

  def post(self, request, *args, **kwargs):
    user = get_object_or_404(models.GitUser, pk=request.POST['creator'])
    repo = get_object_or_404(models.Repository, pk=request.POST['repository'])
    check_permission(self.request, user, repo)
    self.object = self.get_object()
    form_class = self.get_form_class()
    form = self.get_form(form_class)
    env_forms = forms.EnvFormset(self.request.POST, instance=self.object)
    depend_forms = forms.DependencyFormset(self.request.POST, instance=self.object)
    prestep_forms = forms.create_prestep_formset(self.object.creator, self.request.POST, instance=self.object)
    step_forms = forms.create_step_nestedformset(self.object.creator, self.request.POST, instance=self.object)

    valid = form.is_valid() and env_forms.is_valid()
    valid = valid and depend_forms.is_valid() and prestep_forms.is_valid()
    try:
      valid = valid and step_forms.is_valid()
    except:
      # FIXME: This try/except shouldn't really be required
      # but when a user reloads the page in the middle of
      # editing a page the management form seems to get
      # messed up. Instead of responding with
      # a bad error page, this will allow just
      # showing the form again with the error.
      # The fix is in the javascript
      # which isn't setting the fields properly
      # in this case.
      step_forms = forms.create_step_nestedformset(self.object.creator, instance=self.object)
      form.add_error(None, 'Please do not reload the page while editing a recipe. It screws up the form')
      valid = False

    for step in step_forms.forms:
      valid = valid and step.nested.is_valid()

    if valid:
      return self.form_valid(form, env_forms, depend_forms, prestep_forms, step_forms, user, repo)
    else:
      return self.form_invalid(form, env_forms, depend_forms, prestep_forms, step_forms, user, repo)

  def form_valid(self, form, env_forms, depend_forms, prestep_forms, step_forms, user, repo):
    form.cleaned_data['creator_id'] = user.pk
    form.cleaned_data['repository_id'] = repo.pk
    self.object = form.save()
    env_forms.instance = self.object
    env_forms.save()
    depend_forms.instance = self.object
    depend_forms.save()
    prestep_forms.instance = self.object
    prestep_forms.save()
    step_forms.instance = self.object
    self.save_steps(step_forms)

    for f in prestep_forms:
      f.fields['filename'].widget.save_to_disk()

    messages.info(self.request, 'Saved recipe: %s ' % self.object.name )
    try:
      auth_session = user.server.auth().start_session(self.request.session)
      user.server.api().install_webhooks(self.request, auth_session, user, repo)
    except Exception as e:
      messages.warning(self.request, "Failed to install webhook. Error: %s" % e)
    return redirect('ci:view_profile', server_type=user.server.host_type)

  def form_invalid(self, form, env_forms, depend_forms, prestep_forms, step_forms, user, repo):
    messages.error(self.request, 'Failed to save recipe. Please check for errors.')
    return self.get_context(user, repo, form, env_forms, depend_forms, prestep_forms, step_forms)

class RecipeDeleteView(RecipeBaseView, DeleteView):
  model = models.Recipe

  def get_object(self, queryset=None):
    """ Hook to ensure object is owned by request.user. """
    recipe = super(RecipeDeleteView, self).get_object()
    server = recipe.repository.user.server
    auth = server.auth()
    user = auth.signed_in_user(recipe.creator.server, self.request.session)
    check_permission(self.request, user, recipe.repository)
    self.server_type = server.host_type
    self.name = recipe.name
    return recipe

  def get_success_url(self):
    return reverse('ci:view_profile', args=[self.server_type])

  def delete(self, request, *args, **kwargs):
    messages.info(self.request, 'Deleted')
    return super(RecipeDeleteView, self).delete(request, *args, **kwargs)


def list_filenames(request):
  recipes = models.Recipe.objects.order_by('repository').all()
  all_files = []
  for recipe in recipes:
    fnames = set()
    for prestep in recipe.prestepsources.all():
      fnames.add(prestep.filename)
    for step in recipe.steps.all():
      fnames.add(step.filename)
    all_files.append({'files': fnames, 'recipe': recipe})

  return render(request,
      'ci/recipe_filenames.html',
      {'files': all_files}
      )

def check_filenames(request):
  recipes = models.Recipe.objects.all()
  missing = []
  for recipe in recipes:
    prestep_missing = []
    for prestep in recipe.prestepsources.all():
      fname = '{}/{}'.format(settings.RECIPE_BASE_DIR, prestep.filename)
      if not os.path.exists(fname):
        prestep_missing.append(prestep.filename)
    step_missing = []
    for step in recipe.steps.all():
      fname = '{}/{}'.format(settings.RECIPE_BASE_DIR, step.filename)
      if not os.path.exists(fname):
        step_missing.append(step.filename)
    if prestep_missing or step_missing:
      missing.append({'recipe': recipe, 'prestep_missing': prestep_missing, 'step_missing': step_missing})

  return render(request,
      'ci/recipe_missing.html',
      {'missing': missing }
      )
