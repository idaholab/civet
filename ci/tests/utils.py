
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

from __future__ import unicode_literals, absolute_import
from django.conf import settings
from django.test import override_settings
from ci import models
import tempfile
import shutil
import os
import json
import subprocess

def base_git_config(authorized_users=[],
        post_job_status=False,
        post_event_summary=False,
        failed_but_allowed_label_name=None,
        recipe_label_activation={},
        recipe_label_activation_additive={},
        remote_update=False,
        install_webhook=False,
        host_type=None,
        icon_class="",
        remove_pr_label_prefix=["PR: [TODO]"],
        pr_wip_prefix=["WIP:", "[WIP]"],
        hostname="dummy_git_server",
        repo_settings=None,
        ):
    return {"api_url": "https://<api_url>",
            "html_url": "https://<html_url>",
            "hostname": hostname,
            "authorized_users": authorized_users,
            "post_job_status": post_job_status,
            "post_event_summary": post_event_summary,
            "failed_but_allowed_label_name": failed_but_allowed_label_name,
            "recipe_label_activation": recipe_label_activation,
            "recipe_label_activation_additive": recipe_label_activation_additive,
            "remove_pr_label_prefix": ["PR: [TODO]",],
            "remote_update": remote_update,
            "install_webhook": install_webhook,
            "type": host_type,
            "icon_class": icon_class,
            "pr_wip_prefix": pr_wip_prefix,
            "civet_base_url": "https://dummy_civet_server",
            "repository_settings": repo_settings,
            }

def github_config(**kwargs):
    return base_git_config(host_type=settings.GITSERVER_GITHUB, icon_class="dummy github class", **kwargs)

def gitlab_config(**kwargs):
    return base_git_config(host_type=settings.GITSERVER_GITLAB, icon_class="dummy gitlab class", **kwargs)

def bitbucket_config(**kwargs):
    config = base_git_config(host_type=settings.GITSERVER_BITBUCKET, icon_class="dummy bitbucket class", **kwargs)
    config["api1_url"] = config["api_url"]
    config["api2_url"] = config["api_url"]
    return config

def create_git_server(name='dummy_git_server', host_type=settings.GITSERVER_GITHUB):
    server, created = models.GitServer.objects.get_or_create(host_type=host_type, name=name)
    return server

def default_labels():
    return {"DOCUMENTATION": "^docs/",
            "TUTORIAL": "^tutorials/",
            "EXAMPLES": "^examples/",
            }

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
    user.token = json.dumps({'access_token': models.generate_build_key(), 'token_type': 'bearer', 'scope': ["scope"]})
    user.save()
    return user

def get_owner():
    return create_user(name='testmb')

def create_repo(name='testRepo', user=None, server=None):
    if not user:
        user = create_user_with_token(server=server)
    return models.Repository.objects.get_or_create(name=name, user=user)[0]

def create_branch(name='testBranch', user=None, repo=None):
    if not repo:
        repo = create_repo(user=user)
    return models.Branch.objects.get_or_create(name=name, repository=repo)[0]

def create_commit(branch=None, user=None, sha='1234'):
    if not branch:
        branch = create_branch(user=user)
    return models.Commit.objects.get_or_create(branch=branch, sha=sha)[0]

def get_test_user(server=None):
    user = create_user_with_token(name='testmb01', server=server)
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

def create_pr(title='testTitle', number=1, url='http', repo=None, server=None):
    if not repo:
        repo = create_repo(server=server)
    return models.PullRequest.objects.get_or_create(repository=repo, number=number, title=title, url=url)[0]

def create_build_config(name='testBuildConfig'):
    return models.BuildConfig.objects.get_or_create(name=name)[0]

def create_recipe(name='testRecipe', user=None, repo=None, cause=models.Recipe.CAUSE_PULL_REQUEST, branch=None, current=True, scheduler=None):
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
        scheduler=scheduler,
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

def update_job(job, status=None, complete=None, ready=None, active=None, invalidated=None, client=None, created=None):
    if status is not None:
        job.status = status
    if complete is not None:
        job.complete = complete
    if ready is not None:
        job.ready = ready
    if active is not None:
        job.active = active
    if invalidated is not None:
        job.invalidated = invalidated
    if client is not None:
        job.client = client
    if created is not None:
        job.created = created
    job.save()

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

def create_osversion(name="Linux", version="1", other="other"):
    obj, created = models.OSVersion.objects.get_or_create(name=name, version=version, other=other)
    return obj

def create_loadedmodule(name="module"):
    obj, created = models.LoadedModule.objects.get_or_create(name=name)
    return obj

def create_badge(name="badge", repo=None):
    if not repo:
        repo = create_repo()
    return models.RepositoryBadge.objects.get_or_create(name=name, repository=repo)[0]

def _add_git_file(dirname, name):
    p = os.path.join(dirname, name)
    with open(p, 'w') as f:
        f.write(name)
    subprocess.check_output(["git", "add", p], cwd=dirname)

def create_recipe_scripts_dir():
    scripts_dir = tempfile.mkdtemp()
    subprocess.check_output(["git", "init"], cwd=scripts_dir)
    _add_git_file(scripts_dir, '1.sh')
    _add_git_file(scripts_dir, '2.sh')
    subprocess.check_output(["git", "commit", "-m", "'Initial data'"], cwd=scripts_dir)
    return scripts_dir

def create_recipe_dir():
    recipe_dir = tempfile.mkdtemp()
    create_recipes(recipe_dir)
    return recipe_dir

class RecipeDir(object):
    def __init__(self):
        self.name = tempfile.mkdtemp()
        settings.RECIPE_BASE_DIR = self.name
        create_recipes(self.name)

    def __repr__(self):
        return self.name

    @override_settings(RECIPE_BASE_DIR="")
    def __enter__(self):
        return self.name

    def __exit__(self, exc, value, tb):
        shutil.rmtree(self.name)

def create_recipes(recipe_dir):
    subprocess.check_output(["git", "init"], cwd=recipe_dir)
    scripts_dir = os.path.join(recipe_dir, "scripts")
    os.mkdir(scripts_dir)
    os.mkdir(os.path.join(recipe_dir, "recipes"))
    _add_git_file(scripts_dir, '1.sh')
    _add_git_file(scripts_dir, '2.sh')
    _add_git_file(recipe_dir, 'README.md')
    subprocess.check_output(["git", "commit", "-m", "'Initial data'"], cwd=recipe_dir)
    return recipe_dir

class RequestInResponse(object):
    def __init__(self):
        self.url = "someurl"
        self.method = "HTTP METHOD"

class Response(object):
    def __init__(self, json_data=None, content=None, use_links=False, status_code=200, do_raise=False):
        self.status_code = status_code
        self.do_raise = do_raise
        self.reason = "some reason"
        if use_links:
            self.links = {'next': {'url': 'next_url'}}
        else:
            self.links = []

        self.json_data = json_data
        self.content = content
        self.request = RequestInResponse()

    def json(self):
        return self.json_data

    def raise_for_status(self):
        if self.do_raise or self.status_code >= 400:
            raise Exception("Bad status!")


def create_test_jobs():
    """
    Create 4 jobs.
    j0 -> j1, j2 -> j3
    """
    r0 = create_recipe(name="r0")
    r1 = create_recipe(name="r1", user=r0.build_user, repo=r0.repository)
    r2 = create_recipe(name="r2", user=r0.build_user, repo=r0.repository)
    r3 = create_recipe(name="r3", user=r0.build_user, repo=r0.repository)
    r1.depends_on.add(r0)
    r2.depends_on.add(r0)
    r3.depends_on.add(r1)
    r3.depends_on.add(r2)
    ev = create_event(user=r0.build_user)
    job0 = create_job(recipe=r0, event=ev)
    job1 = create_job(recipe=r1, event=ev)
    job2 = create_job(recipe=r2, event=ev)
    job3 = create_job(recipe=r3, event=ev)
    create_step_result(job=job0)
    create_step_result(job=job1)
    create_step_result(job=job2)
    create_step_result(job=job3)
    return (job0, job1, job2, job3)
