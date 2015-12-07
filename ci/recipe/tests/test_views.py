from django.test import TestCase, Client
from django.test.client import RequestFactory
from django.core.urlresolvers import reverse
from django.conf import settings
from mock import patch
from ci import models, github
from ci.tests import utils
import shutil

class ViewsTestCase(TestCase):
  fixtures = ['base']

  def setUp(self):
    self.client = Client()
    self.factory = RequestFactory()
    self.user = utils.get_test_user()
    self.repo = self.user.repositories.first()
    self.recipe = utils.create_recipe(user=self.user, repo=self.repo)
    self.step = utils.create_step(recipe=self.recipe)
    self.recipe_dir, self.git = utils.create_recipe_dir()
    settings.RECIPE_BASE_DIR = self.recipe_dir

  def tearDown(self):
    shutil.rmtree(self.recipe_dir)

  def formset_data(self, prefix, total=0, initial=0, min_forms=0, max_forms=1000):
    return {
        '{}-TOTAL_FORMS'.format(prefix): total,
        '{}-INITIAL_FORMS'.format(prefix): initial,
        '{}-MIN_FORMS'.format(prefix): min_forms,
        '{}-MAX_FORMS'.format(prefix): min_forms,
        '{}-id'.format(prefix): '',
        '{}-DELETE'.format(prefix): False,
        }

  def form_data(self,
    name='testRecipe',
    display_name='display name',
    creator=None,
    repository=None,
    branch="",
    abort_on_failure=True,
    private=False,
    active=True,
    cause=models.Recipe.CAUSE_PULL_REQUEST,
    config=None,
    auto_authorized=0,
    automatic=models.Recipe.MANUAL,
    priority=0,
    ):
    return {
        'name': name,
        'display_name': name,
        'creator': creator.pk,
        'repository': repository.pk,
        'branch': branch,
        'abort_on_failure': abort_on_failure,
        'private': private,
        'active': active,
        'cause': cause,
#        'auto_authorized': auto_authorized,
        'build_configs': config.pk,
        'automatic': automatic,
        'priority': priority,
        }

  def set_formset_data(self, data, base, parent=None, obj=None, delete=False):
    if parent:
      data['{}-recipe'.format(base)] = parent.pk
    else:
      data['{}-recipe'.format(base)] = ''

    data['{}-DELETE'.format(base)] = delete
    if obj:
      data['{}-id'.format(base)] = obj.pk
    else:
      data['{}-id'.format(base)] = ''

  def new_recipe_dependency(self, data, idx):
    base = 'recipedependency_set-{}'.format(idx)
    depend_name = '{}-dependency'.format(base)
    abort_name = '{}-abort-on-failure'.format(base)
    data[depend_name] = ''
    data[abort_name] = ''
    total_key = 'recipedependency_set-TOTAL_FORMS'
    data[total_key] = data[total_key] + 1
    self.set_formset_data(data, base)
    return data

  def new_env_var(self, data, idx):
    base = 'environment_vars-{}'.format(idx)
    name_key = '{}-name'.format(base)
    value_key = '{}-value'.format(base)
    data[name_key] = ''
    data[value_key] = ''
    total_key = 'environment_vars-TOTAL_FORMS'
    data[total_key] = data[total_key] + 1
    self.set_formset_data(data, base)
    return data

  def new_prestep(self, data, idx):
    base = 'prestepsources-{}'.format(idx)
    fname0_key = '{}-filename_0'.format(base)
    fname1_key = '{}-filename_1'.format(base)
    fname2_key = '{}-filename_2'.format(base)
    data[fname0_key] = ''
    data[fname1_key] = ''
    data[fname2_key] = ''
    total_key = 'prestepsources-TOTAL_FORMS'
    data[total_key] = data[total_key] + 1
    self.set_formset_data(data, base)
    return data

  def new_step_env(self, data, step_idx, env_idx):
    base = 'steps-{}-step_environment-{}'.format(step_idx, env_idx)
    data['{}-name'] = ''
    data['{}-value'] = ''
    total_key = 'steps-{}-step_environment-TOTAL_FORMS'.format(step_idx)
    data[total_key] += 1
    data['{}-step'.format(base)] = ''
    data['{}-id'.format(base)] = ''
    data['{}-DELETE'.format(base)] = ''
    return data

  def new_step(self, data, idx):
    base = 'steps-{}'.format(idx)
    fname0_key = '{}-filename_0'.format(base)
    fname1_key = '{}-filename_1'.format(base)
    fname2_key = '{}-filename_2'.format(base)
    data['{}-name'.format(base)] = ''
    data['{}-position'.format(base)] = idx
    data['{}-abort_on_failure'.format(base)] = True
    data[fname0_key] = ''
    data[fname1_key] = ''
    data[fname2_key] = ''
    total_key = 'steps-TOTAL_FORMS'
    data[total_key] = data[total_key] + 1
    data['{}-step'] = ''
    env_base = '{}-step_environment'.format(base)
    data.update(self.formset_data(env_base))
    return data

  def env_vars_data(self, idx, recipe=None, delete=False, env=None):
    base = 'environment_vars-{}'.format(idx)
    name_key = '{}-name'.format(base)
    value_key = '{}-value'.format(base)
    data = {name_key: '', value_key: ''}
    if env:
      data[name_key] = env.name
      data[value_key] = env.value
    self.set_formset_data(data, base, recipe, env, delete)
    return data

  def prestep_data(self, idx, recipe=None, delete=False, prestep=None):
    base = 'prestepsources-{}'.format(idx)
    fname0_key = '{}-filename_0'.format(base)
    fname1_key = '{}-filename_1'.format(base)
    fname2_key = '{}-filename_2'.format(base)
    data = {fname0_key: '', fname1_key: '', fname2_key: ''}
    if prestep:
      data[fname0_key] = prestep.filename
      data[fname1_key] = prestep.filename
      data[fname2_key] = '1.sh'
    self.set_formset_data(data, base, recipe, prestep, delete)
    return data

  def step_data(self, idx, recipe=None, delete=False, step=None):
    base = 'steps-{}'.format(idx)
    name_key = '{}-name'.format(base)
    abort_key = '{}-abort_on_failure'.format(base)
    position_key = '{}-position'.format(base)
    env_base = '{}-step_environment'.format(base)
    fname0_key= '{}-filename_0'.format(base)
    fname1_key= '{}-filename_1'.format(base)
    fname2_key= '{}-filename_2'.format(base)
    data = {name_key: '', fname0_key: '', fname1_key: '', fname2_key: ''}
    data.update(self.formset_data(env_base))
    if step:
      data[name_key] = step.name
      #print('setting name to {}'.format(step.name))
      data[abort_key] = step.abort_on_failure
      data[fname0_key] = step.filename
      data[fname1_key] = step.filename
      data[fname2_key] = '1.sh'
      data[position_key] = step.position
      data.update(self.formset_data(env_base, total=step.step_environment.count()))
      for i, env in enumerate(step.step_environment.all()):
        new_env_base = '{}-{}'.format(env_base, idx)
        env_name_key = '{}-name'.format(new_env_base)
        env_value_key = '{}-value'.format(new_env_base)
        data[env_name_key] = env.name
        data[env_value_key] = env.value
        self.set_formset_data(data, new_env_base, step, delete, env)

    self.set_formset_data(data, base, recipe, step, delete)
    return data

  def set_data_from_recipe(self, data, recipe):
    for i, env in enumerate(recipe.environment_vars.all()):
      data.update(self.env_vars_data(i, recipe, False, env))
      data.update(self.formset_data('environment_vars', total=recipe.environment_vars.count()))

    for i, depend in enumerate(recipe.all_dependencies.all()):
      data.update(self.recipe_dependency_data(i, recipe, False, depend))
      data.update(self.formset_data('recipedependency_set', total=recipe.all_dependencies.count()))

    for i, prestep in enumerate(recipe.prestepsources.all()):
      data.update(self.prestep_data(i, recipe, False, prestep))
      data.update(self.formset_data('prestepsources', total=recipe.prestepsources.count()))

    for i, step in enumerate(recipe.steps.all()):
      data.update(self.step_data(i, recipe=recipe, delete=False, step=step))
      data.update(self.formset_data('steps', total=recipe.steps.count()))
    return data

  def default_form_data(self):
    config = models.BuildConfig.objects.first()
    data = self.form_data(name='edited_name', creator=self.user, config=config, repository=self.repo)
    data.update(self.formset_data('recipedependency_set'))
    data.update(self.formset_data('environment_vars'))
    data.update(self.formset_data('prestepsources'))
    data.update(self.formset_data('steps'))
    return data

  @patch.object(github.api.GitHubAPI, 'get_branches')
  def test_edit_get(self, branches_mock):
    branches_mock.return_value = ['devel', 'master']
    url = reverse('ci:recipe:edit', args=[self.recipe.pk])
    response = self.client.get(url)
    self.assertEqual(response.status_code, 403)

    utils.simulate_login(self.client.session, self.user)
    response = self.client.get(url)
    self.assertEqual(response.status_code, 200)

    recipe = utils.create_recipe()
    # random recipe not owned by our test_user, so should fail
    url = reverse('ci:recipe:edit', args=[recipe.pk])
    response = self.client.get(url)
    self.assertEqual(response.status_code, 403)

  def test_edit_post(self):
    self.step.position = 0
    fname = '{}/1.sh'.format(self.user.name)
    self.step.filename = fname
    self.step.save()
    data = self.default_form_data()
    data = self.set_data_from_recipe(data, self.recipe)
    url = reverse('ci:recipe:edit', args=[self.recipe.pk])
    response = self.client.post(url, data)
    self.assertEqual(response.status_code, 403)

    num_before = models.Recipe.objects.count()

    utils.simulate_login(self.client.session, self.user)
    response = self.client.post(url, data)
    #print(response)
    self.assertEqual(response.status_code, 302) #redirect

    # should be valid
    self.new_prestep(data, 0)
    data['prestepsources-0-filename_0'] = fname
    data['prestepsources-0-filename_1'] = fname
    data['prestepsources-0-filename_2'] = '1.sh'
    response = self.client.post(url, data)
    #print(response)
    self.assertEqual(response.status_code, 302) #redirect
    num_after = models.Recipe.objects.count()
    self.assertEqual(num_before, num_after)
    new_recipe = models.Recipe.objects.get(pk=self.recipe.pk)
    self.assertEqual(data['name'], new_recipe.name)

    # submit a bad form
    data['name'] = ''
    response = self.client.post(url, data)
    self.assertEqual(response.status_code, 200) #no redirect

  def test_add_get(self):
    url = reverse('ci:recipe:add')
    recipe = utils.create_recipe()
    response = self.client.get(url)
    # no user_id
    self.assertEqual(response.status_code, 404)
    data = {'user_id': self.user.pk}

    # no repo
    response = self.client.get(url, data)
    self.assertEqual(response.status_code, 404)

    data['repo'] = str(self.repo)
    # no recipe_copy
    response = self.client.get(url, data)
    self.assertEqual(response.status_code, 404)

    data['recipe_copy'] = recipe.pk
    # not signed in
    response = self.client.get(url, data)
    self.assertEqual(response.status_code, 403)

    # ok
    utils.simulate_login(self.client.session, self.user)
    response = self.client.get(url, data)
    self.assertEqual(response.status_code, 200)

    repo = utils.create_repo()
    # random repo not owned by our test_user, so should fail
    data['repo'] = str(repo)
    response = self.client.get(url, data)
    self.assertEqual(response.status_code, 403)

  def test_add_post(self):
    data = self.default_form_data()
    url = reverse('ci:recipe:add')
    # not logged in
    response = self.client.post(url, data)
    self.assertEqual(response.status_code, 403)

    num_before = models.Recipe.objects.count()

    # ok, submit a basic form
    utils.simulate_login(self.client.session, self.user)
    response = self.client.post(url, data)
    self.assertEqual(response.status_code, 302) #redirect
    num_after = models.Recipe.objects.count()
    self.assertEqual(num_before+1, num_after)

    # submit a bad form
    utils.simulate_login(self.client.session, self.user)
    data['name'] = ''
    response = self.client.post(url, data)
    self.assertEqual(response.status_code, 200) #no redirect

  def test_add_dependency(self):
    url = reverse('ci:recipe:add')
    utils.simulate_login(self.client.session, self.user)
    data = self.default_form_data()
    recipe2 = utils.create_recipe(user=self.user, repo=self.repo, name='recipe2')
    self.new_recipe_dependency(data, 0)
    data['recipedependency_set-0-dependency'] = recipe2.pk

    num_before = models.Recipe.objects.count()
    depend_before = models.RecipeDependency.objects.count()
    response = self.client.post(url, data)
    self.assertEqual(response.status_code, 302) #redirect
    num_after = models.Recipe.objects.count()
    depend_after = models.RecipeDependency.objects.count()
    self.assertEqual(num_before+1, num_after)
    self.assertEqual(depend_before+1, depend_after)
    recipe = models.Recipe.objects.last()
    depend = models.RecipeDependency.objects.last()
    self.assertEqual(depend.recipe, recipe)
    self.assertEqual(depend.dependency, recipe2)

  def test_add_env_var(self):
    url = reverse('ci:recipe:add')
    utils.simulate_login(self.client.session, self.user)
    data = self.default_form_data()
    self.new_env_var(data, 0)
    data['environment_vars-0-name'] = 'name'
    data['environment_vars-0-value'] = 'value'

    num_before = models.Recipe.objects.count()
    env_before = models.RecipeEnvironment.objects.count()
    response = self.client.post(url, data)
    self.assertEqual(response.status_code, 302) #redirect
    num_after = models.Recipe.objects.count()
    env_after = models.RecipeEnvironment.objects.count()
    self.assertEqual(num_before+1, num_after)
    self.assertEqual(env_before+1, env_after)
    recipe = models.Recipe.objects.last()
    env = models.RecipeEnvironment.objects.last()
    self.assertEqual(env.recipe, recipe)
    self.assertEqual(env.name, 'name')
    self.assertEqual(env.value, 'value')

  def test_add_prestep(self):
    url = reverse('ci:recipe:add')
    utils.simulate_login(self.client.session, self.user)
    data = self.default_form_data()
    self.new_prestep(data, 0)
    fname = '{}/1.sh'.format(self.user.name)
    data['prestepsources-0-filename_0'] = fname
    data['prestepsources-0-filename_1'] = fname
    data['prestepsources-0-filename_2'] = '1.sh'

    num_before = models.Recipe.objects.count()
    prestep_before = models.PreStepSource.objects.count()
    response = self.client.post(url, data)
    self.assertEqual(response.status_code, 302) #redirect
    num_after = models.Recipe.objects.count()
    prestep_after = models.PreStepSource.objects.count()
    self.assertEqual(num_before+1, num_after)
    self.assertEqual(prestep_before+1, prestep_after)
    recipe = models.Recipe.objects.last()
    prestep = models.PreStepSource.objects.last()
    self.assertEqual(prestep.recipe, recipe)
    self.assertEqual(prestep.filename, fname)

  def test_add_step(self):
    url = reverse('ci:recipe:add')
    utils.simulate_login(self.client.session, self.user)
    data = self.default_form_data()
    self.new_step(data, 0)
    fname = '{}/1.sh'.format(self.user.name)
    data['steps-0-filename_0'] = fname
    data['steps-0-filename_1'] = fname
    data['steps-0-filename_2'] = '1.sh'
    data['steps-0-name'] = 'new_step'
    data['steps-0-position'] = 0
    data = self.new_step_env(data, 0, 0)
    data['steps-0-step_environment-0-name'] = 'name'
    data['steps-0-step_environment-0-value'] = 'value'

    num_before = models.Recipe.objects.count()
    step_before = models.Step.objects.count()
    env_before = models.StepEnvironment.objects.count()
    response = self.client.post(url, data)
    self.assertEqual(response.status_code, 302) #redirect
    num_after = models.Recipe.objects.count()
    step_after = models.Step.objects.count()
    env_after = models.StepEnvironment.objects.count()
    self.assertEqual(num_before+1, num_after)
    self.assertEqual(step_before+1, step_after)
    self.assertEqual(env_before+1, env_after)
    recipe = models.Recipe.objects.order_by('-pk').first()
    step = models.Step.objects.order_by('-pk').first()
    self.assertEqual(step.filename, fname)
    self.assertEqual(step.position, 0)
    self.assertEqual(step.name, 'new_step')
    self.assertEqual(step.step_environment.count(), 1)
    self.assertEqual(step.step_environment.first().name, 'name')
    self.assertEqual(step.step_environment.first().value, 'value')
    self.assertEqual(recipe.display_name, 'edited_name')
    self.assertEqual(step.recipe, recipe)

  def test_list_filenames(self):
    url = reverse('ci:recipe:list_filenames')
    utils.create_prestepsource(recipe=self.recipe)
    response = self.client.get(url)
    self.assertEqual(response.status_code, 200)

  def test_check_filenames(self):
    prestep = utils.create_prestepsource(recipe=self.recipe)
    url = reverse('ci:recipe:check')
    # both filenames for prestep and step are invalid
    response = self.client.get(url)
    self.assertEqual(response.status_code, 200)
    self.assertNotIn('None', response.content)

    # step should still be invalid
    prestep.filename = 'common/1.sh'
    prestep.save()
    response = self.client.get(url)
    self.assertEqual(response.status_code, 200)
    self.assertNotIn('None', response.content)

    self.step.filename = 'common/1.sh'
    self.step.save()
    # both should be fine now
    response = self.client.get(url)
    self.assertEqual(response.status_code, 200)
    self.assertIn('None', response.content)

  def test_delete(self):
    url = reverse('ci:recipe:delete', args=[self.recipe.pk,])

    #not signed in
    response = self.client.post(url)
    self.assertEqual(response.status_code, 403)

    utils.simulate_login(self.client.session, self.user)
    # should be ok
    response = self.client.post(url)
    self.assertEqual(response.status_code, 302)
