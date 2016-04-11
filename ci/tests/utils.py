from django.conf import settings
from ci import models
import tempfile, os
from os import path
import git
import json


def create_git_server(name='github.com', base_url='http://base', host_type=settings.GITSERVER_GITHUB):
  server, created = models.GitServer.objects.get_or_create(host_type=host_type)
  if created:
    server.name = name
    server.base_url = base_url
    server.save()
  return server


def simulate_login(session, user):
  """
  Helper function to simulate signing in to github
  """
  tmp_session = session # copying to a variable is required
  user.server.auth().set_browser_session_from_user(tmp_session, user)
  tmp_session.save()

def create_user(name='testUser', server=None):
  if not server:
    server = create_git_server()
  return models.GitUser.objects.get_or_create(name=name, server=server)[0]

def create_user_with_token(name='testUser', server=None):
  user = create_user(name, server=server)
  # the token isn't the build key but just use it for the random number
  user.token = json.dumps({'access_token':models.generate_build_key(), 'token_type': 'bearer', 'scope': '["scope"]'})
  user.save()
  return user

def get_owner():
  return create_user(name='testmb')

def create_repo(name='testRepo', user=None):
  if not user:
    user = create_user_with_token()
  return models.Repository.objects.get_or_create(name=name, user=user)[0]

def create_branch(name='testBranch', user=None, repo=None):
  if not repo:
    repo = create_repo(user=user)
  return models.Branch.objects.get_or_create(name=name, repository=repo)[0]

def create_commit(branch=None, user=None, sha='1234'):
  if not branch:
    branch = create_branch(user=user)
  return models.Commit.objects.get_or_create(branch=branch, sha=sha)[0]

def get_test_user():
  user = create_user_with_token(name='testmb01')
  repo = create_repo(name='repo01', user=user)
  branch = create_branch(name='branch01', repo=repo)
  create_commit(branch=branch, sha='sha01')
  return user

def create_event(user=None, commit1='1234', commit2='2345', branch1=None, branch2=None, cause=models.Event.PULL_REQUEST):
  if not user:
    user = create_user_with_token()
  c1 = create_commit(user=user, branch=branch1, sha=commit1)
  c2 = create_commit(user=user, branch=branch2, sha=commit2)
  return models.Event.objects.get_or_create(head=c1, base=c2, cause=cause, build_user=user)[0]

def create_pr(title='testTitle', number=1, url='http', repo=None):
  if not repo:
    repo = create_repo()
  return models.PullRequest.objects.get_or_create(repository=repo, number=number, title=title, url=url)[0]

def create_build_config(name='testBuildConfig'):
  return models.BuildConfig.objects.get_or_create(name=name)[0]

def create_recipe(name='testRecipe', user=None, repo=None, cause=models.Recipe.CAUSE_PULL_REQUEST, branch=None, current=True):
  if not user:
    user = create_user_with_token()
  if not repo:
    repo = create_repo(user=user)

  recipe, created = models.Recipe.objects.get_or_create(
      name=name,
      display_name=name,
      build_user=user,
      repository=repo,
      private=True,
      active=True,
      cause=cause,
      filename=name,
      )
  recipe.build_configs.add(create_build_config())
  recipe.branch = branch
  recipe.current = current
  recipe.save()
  return recipe

def create_step(name='testStep', filename='default.sh', recipe=None, position=0):
  if not recipe:
    recipe = create_recipe()
  return models.Step.objects.get_or_create(recipe=recipe, name=name, position=position, filename=filename)[0]

def create_recipe_environment(name='testEnv', value='testValue', recipe=None):
  if not recipe:
    recipe = create_recipe()
  return models.RecipeEnvironment.objects.get_or_create(name=name, value=value, recipe=recipe)[0]

def create_recipe_dependency(recipe=None, depends_on=None):
  if not recipe:
    recipe = create_recipe(name="recipe1")
  if not depends_on:
    depends_on = create_recipe(name="recipe2")

  recipe.depends_on.add(depends_on)
  return recipe, depends_on

def create_step_environment(name='testEnv', value='testValue', step=None):
  if not step:
    step = create_step()
  return models.StepEnvironment.objects.get_or_create(step=step, name=name, value=value)[0]

def create_job(recipe=None, event=None, config=None, user=None):
  if not recipe:
    recipe = create_recipe(user=user)
  if not event:
    event = create_event(user=user)
  if not config:
    config = recipe.build_configs.first()
  return models.Job.objects.get_or_create(config=config, recipe=recipe, event=event)[0]

def create_prestepsource(filename="default.sh", recipe=None):
  if not recipe:
    recipe = create_recipe()
  return models.PreStepSource.objects.get_or_create(recipe=recipe, filename=filename)[0]

def create_client(name='testClient', ip='127.0.0.1'):
  obj, created = models.Client.objects.get_or_create(name=name, ip=ip)
  return obj

def create_step_result(status=models.JobStatus.NOT_STARTED, step=None, job=None, name="step result", position=0):
  if not job:
    job = create_job()
  if not step:
    step = create_step(recipe=job.recipe, name=name, position=position)
  result, created = models.StepResult.objects.get_or_create(job=job, name=step.name, position=step.position, abort_on_failure=step.abort_on_failure, filename=step.filename)
  result.status = status
  result.save()
  return result

def _write_file(repo, dirname, name):
  p = path.join(dirname, name)
  with open(p, 'w') as f:
    f.write(name)
  repo.index.add([p])

def _create_subdir(recipe_dir, repo, name):
  # create some set files and directories
  d = path.join(recipe_dir, name)
  os.mkdir(d)
  _write_file(repo, d, '1.sh')
  _write_file(repo, d, '2.sh')

  subdir0 = path.join(d, 'subdir0')
  os.mkdir(subdir0)
  _write_file(repo, subdir0, '1.sh')
  _write_file(repo, subdir0, '2.sh')

  subdir1 = path.join(d, 'subdir1')
  os.mkdir(subdir1)
  _write_file(repo, subdir1, '1.sh')
  _write_file(repo, subdir1, '2.sh')

def create_recipe_dir():
  recipe_dir = tempfile.mkdtemp()
  repo = git.Repo.init(recipe_dir)
  _create_subdir(recipe_dir, repo, 'scripts')
  _create_subdir(recipe_dir, repo, 'test')
  repo.index.commit('Initial data')
  return recipe_dir, repo

class Response(object):
    def __init__(self, json_data=None, content=None, use_links=False, status_code=200, do_raise=False):
      self.status_code = status_code
      self.do_raise = do_raise
      if use_links:
        self.links = {'next': {'url': 'next_url'}}
      else:
        self.links = []

      self.json_data = json_data
      self.content = content

    def json(self):
      return self.json_data

    def raise_for_status(self):
      if self.do_raise:
        raise Exception("Bad status!")
