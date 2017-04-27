
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

from django.test import TestCase
from django.conf import settings
from ci import models
from . import utils
import math

class Tests(TestCase):
#  fixtures = ['base', 'dummy']

    def test_git_server(self):
        server = utils.create_git_server(host_type=settings.GITSERVER_GITHUB)
        self.assertTrue(isinstance(server, models.GitServer))
        self.assertEqual(server.__unicode__(), server.name)
        self.assertNotEqual(server.api(), None)
        self.assertNotEqual(server.auth(), None)
        icon_class = server.icon_class()
        self.assertEqual(icon_class, "fa fa-github fa-lg")
        server = utils.create_git_server(host_type=settings.GITSERVER_GITLAB)
        self.assertNotEqual(server.api(), None)
        self.assertNotEqual(server.auth(), None)
        icon_class = server.icon_class()
        self.assertEqual(icon_class, "fa fa-gitlab fa-lg")
        server = utils.create_git_server(host_type=settings.GITSERVER_BITBUCKET)
        self.assertNotEqual(server.api(), None)
        self.assertNotEqual(server.auth(), None)
        icon_class = server.icon_class()
        self.assertEqual(icon_class, "fa fa-bitbucket fa-lg")

    def test_git_user(self):
        user = utils.create_user()
        self.assertTrue(isinstance(user, models.GitUser))
        self.assertEqual(user.__unicode__(), user.name)
        session = user.start_session()
        self.assertNotEqual(session, None)
        self.assertNotEqual(user.api(), None)
        self.assertEqual(user.token, '')

    def test_repository(self):
        repo = utils.create_repo()
        self.assertTrue(isinstance(repo, models.Repository))
        self.assertIn(repo.name, repo.__unicode__())
        self.assertIn(repo.user.name, repo.__unicode__())
        url = repo.url()
        self.assertIn(repo.user.name, url)
        self.assertIn(repo.name, url)
        git_url = repo.git_url()
        self.assertIn(repo.user.name, git_url)
        self.assertIn(repo.name, git_url)

    def test_branch(self):
        branch = utils.create_branch()
        self.assertTrue(isinstance(branch, models.Branch))
        self.assertIn(branch.repository.name, branch.__unicode__())
        self.assertIn(branch.repository.user.name, branch.__unicode__())
        self.assertIn(branch.name, branch.__unicode__())
        server = branch.server()
        self.assertEqual(server, branch.repository.user.server)
        user = branch.user()
        self.assertEqual(user, branch.repository.user)
        self.assertNotEqual(branch.status_slug(), None)

    def test_commit(self):
        commit = utils.create_commit()
        self.assertTrue(isinstance(commit, models.Commit))
        self.assertIn(commit.branch.name, commit.__unicode__())
        self.assertIn(commit.sha, commit.__unicode__())
        self.assertEqual(commit.server(), commit.branch.repository.user.server)
        self.assertEqual(commit.repo(), commit.branch.repository)
        self.assertNotEqual(commit.url(), None)

    def test_event_sorted_jobs(self):
        """
        Had the scenario where we have:
          Precheck -> Test:linux, Test:clang -> Merge
        where Test had 2 build configs.
        But the merge recipe had a depends_on with an outdated
        recipe
        get_sorted_jobs didn't seem to work.
        """
        event = utils.create_event()
        event.cause = models.Event.PUSH
        event.save()

        r0 = utils.create_recipe(name='precheck')
        r1 = utils.create_recipe(name='test')
        r2 = utils.create_recipe(name='merge')
        r3 = utils.create_recipe(name='test')
        # These two need to have the same filename
        r1.filename = "my filename"
        r1.save()
        r3.filename = r1.filename
        r3.save()

        r1.build_configs.add(utils.create_build_config("Otherconfig"))
        utils.create_recipe_dependency(recipe=r1 , depends_on=r0)
        utils.create_recipe_dependency(recipe=r2, depends_on=r3)
        j0 = utils.create_job(recipe=r0, event=event)
        j1a = utils.create_job(recipe=r1, event=event, config=r1.build_configs.first())
        j1b = utils.create_job(recipe=r1, event=event, config=r1.build_configs.last())
        j2 = utils.create_job(recipe=r2, event=event)
        job_groups = event.get_sorted_jobs()
        self.assertEqual(len(job_groups), 3)
        self.assertEqual(len(job_groups[0]), 1)
        self.assertIn(j0, job_groups[0])
        self.assertEqual(len(job_groups[1]), 2)
        self.assertIn(j1a, job_groups[1])
        self.assertIn(j1b, job_groups[1])
        self.assertEqual(len(job_groups[2]), 1)
        self.assertIn(j2, job_groups[2])

    def test_event(self):
        event = utils.create_event()
        self.assertTrue(isinstance(event, models.Event))
        self.assertIn('Pull', event.__unicode__())
        self.assertIn('Pull', event.cause_str())
        event.cause = models.Event.PUSH
        event.save()
        self.assertIn('Push', event.cause_str())
        # duplicate commits
        with self.assertRaises(Exception):
            utils.create_event()
        user = event.user()
        self.assertEqual(event.head.user(), user)
        self.assertNotEqual(event.status_slug(), None)
        self.assertEqual(event.is_manual(), False)

        r0 = utils.create_recipe(name='r0')
        r1 = utils.create_recipe(name='r1')
        r2 = utils.create_recipe(name='r2')
        r3 = utils.create_recipe(name='r3')
        r4 = utils.create_recipe(name='r4')
        r4.build_configs.add(utils.create_build_config("Otherconfig"))
        utils.create_recipe_dependency(recipe=r1 , depends_on=r0)
        utils.create_recipe_dependency(recipe=r3, depends_on=r0)
        utils.create_recipe_dependency(recipe=r4, depends_on=r0)
        utils.create_recipe_dependency(recipe=r2, depends_on=r1)
        utils.create_recipe_dependency(recipe=r2, depends_on=r3)
        utils.create_recipe_dependency(recipe=r2, depends_on=r4)
        j0 = utils.create_job(recipe=r0, event=event)
        j1 = utils.create_job(recipe=r1, event=event)
        j2 = utils.create_job(recipe=r2, event=event)
        j3 = utils.create_job(recipe=r3, event=event)
        j4a = utils.create_job(recipe=r4, event=event, config=r4.build_configs.first())
        j4b = utils.create_job(recipe=r4, event=event, config=r4.build_configs.last())
        j0.recipe.priority = 1
        j0.recipe.display_name = 'r0'
        j0.recipe.save()
        j1.recipe.priority = 10
        j1.recipe.display_name = 'r1'
        j1.recipe.save()
        j2.recipe.priority = 1
        j2.recipe.display_name = 'r2'
        j2.recipe.save()
        self.assertEqual(models.sorted_job_compare(j0, j1), 1)
        self.assertEqual(models.sorted_job_compare(j1, j0), -1)
        self.assertEqual(models.sorted_job_compare(j0, j2), -1)
        self.assertEqual(models.sorted_job_compare(j2, j0), 1)
        self.assertEqual(models.sorted_job_compare(j0, j0), 0)
        job_groups = event.get_sorted_jobs()
        self.assertEqual(len(job_groups), 3)
        self.assertEqual(len(job_groups[0]), 1)
        self.assertIn(j0, job_groups[0])
        self.assertEqual(len(job_groups[1]), 4)
        self.assertIn(j1, job_groups[1])
        self.assertIn(j3, job_groups[1])
        self.assertIn(j4a, job_groups[1])
        self.assertIn(j4b, job_groups[1])
        self.assertEqual(len(job_groups[2]), 1)
        self.assertIn(j2, job_groups[2])

        j2.recipe.display_name = 'r0'
        j2.recipe.save()
        self.assertEqual(models.sorted_job_compare(j2, j0), 0)
        self.assertEqual(models.sorted_job_compare(j0, j2), 0)

        j2.config = utils.create_build_config("Aconfig")
        self.assertEqual(models.sorted_job_compare(j2, j0), -1)
        self.assertEqual(models.sorted_job_compare(j0, j2), 1)

        self.assertEqual(event.get_changed_files(), [])
        changed = ["foo/bar", "bar/foo"]
        event.set_changed_files(changed)
        event.save()
        self.assertEqual(event.get_changed_files(), changed)

        self.assertEqual(event.get_json_data(), None)
        json_data = ["foo"]
        event.set_json_data(json_data)
        event.save()
        self.assertEqual(event.get_json_data(), json_data)

    def test_pullrequest(self):
        pr = utils.create_pr()
        self.assertTrue(isinstance(pr, models.PullRequest))
        self.assertIn(pr.title, pr.__unicode__())
        self.assertNotEqual(pr.status_slug(), None)

    def test_buildconfig(self):
        bc = utils.create_build_config()
        self.assertTrue(isinstance(bc, models.BuildConfig))
        self.assertIn(bc.name, bc.__unicode__())

    def test_recipe(self):
        rc = utils.create_recipe()
        self.assertTrue(isinstance(rc, models.Recipe))
        self.assertIn(rc.name, rc.__unicode__())

        self.assertEqual(rc.auto_str(), models.Recipe.AUTO_CHOICES[rc.automatic][1])
        self.assertEqual(rc.cause_str(), models.Recipe.CAUSE_CHOICES[rc.cause][1])
        self.assertTrue(isinstance(rc.configs_str(), basestring))

        rc.cause = models.Recipe.CAUSE_PUSH
        rc.branch = utils.create_branch()
        rc.save()
        self.assertIn('Push', rc.cause_str())

        utils.create_recipe_dependency(recipe=rc)
        self.assertEqual(rc.depends_on.first().display_name, rc.dependency_str())

    def dependency_str(self):
        return ', '.join([ dep.display_name for dep in self.depends_on.all() ])

    def test_recipeenv(self):
        renv = utils.create_recipe_environment()
        self.assertTrue(isinstance(renv, models.RecipeEnvironment))
        self.assertIn(renv.name, renv.__unicode__())
        self.assertIn(renv.value, renv.__unicode__())

    def test_prestepsource(self):
        s = utils.create_prestepsource()
        self.assertTrue(isinstance(s, models.PreStepSource))
        self.assertIn(s.filename, s.__unicode__())

    def test_step(self):
        s = utils.create_step()
        self.assertTrue(isinstance(s, models.Step))
        self.assertIn(s.name, s.__unicode__())

    def test_stepenvironment(self):
        se = utils.create_step_environment()
        self.assertTrue(isinstance(se, models.StepEnvironment))
        self.assertIn(se.name, se.__unicode__())
        self.assertIn(se.value, se.__unicode__())

    def test_client(self):
        c = utils.create_client()
        self.assertTrue(isinstance(c, models.Client))
        self.assertIn(c.name, c.__unicode__())
        self.assertNotEqual(c.status_str(), '')
        self.assertGreater(c.unseen_seconds(), 0)

    def test_job(self):
        j = utils.create_job()
        j.status = models.JobStatus.NOT_STARTED
        j.save()
        self.assertTrue(isinstance(j, models.Job))
        self.assertIn(j.recipe.name, j.__unicode__())
        self.assertEqual(None, j.failed_result())
        self.assertEqual(j.status_slug(), 'Not_Started')
        self.assertEqual(j.status_str(), 'Not started')
        self.assertEqual(j.active_results().count(), 0)
        j.status = models.JobStatus.FAILED
        j.save()
        result = utils.create_step_result(job=j)
        self.assertEqual(None, j.failed_result())

        result.status = models.JobStatus.FAILED
        result.save()
        self.assertEqual(result, j.failed_result())

        result.status = models.JobStatus.FAILED_OK
        result.save()
        self.assertEqual(result, j.failed_result())
        self.assertEqual(j.total_output_size(), "0.0 B")

        j.status = models.JobStatus.NOT_STARTED
        j.active = False
        j.save()
        self.assertEqual(j.status_slug(), 'Activation_Required')
        self.assertEqual(j.status_str(), 'Requires activation')

        self.assertEqual(j.unique_name(), j.recipe.display_name)
        config = utils.create_build_config("anotherConfig")
        j.recipe.build_configs.add(config)
        self.assertIn(j.recipe.display_name, j.unique_name())
        self.assertIn(j.config.name, j.unique_name())

    def test_stepresult(self):
        sr = utils.create_step_result()
        sr.output = '&<\n\33[30mfoo\33[0m'
        sr.save()
        self.assertTrue(isinstance(sr, models.StepResult))
        self.assertIn(sr.name, sr.__unicode__())
        self.assertEqual(models.JobStatus.to_slug(sr.status), sr.status_slug())
        self.assertEqual(sr.clean_output(), '&amp;&lt;<br/><span class="term-fg30">foo</span>')
        self.assertEqual(sr.plain_output(), "&<\nfoo")
        sr.output = 'a'
        sr.save()
        self.assertEqual(sr.output_size(), '1.0 B')
        sr.output = "a" * 1024 * 1024 * 3
        sr.save()
        self.assertTrue(sr.clean_output().startswith("Output too large"))

    def test_generate_build_key(self):
        build_key = models.generate_build_key()
        self.assertNotEqual('', build_key)

    def test_jobstatus(self):
        for i in models.JobStatus.STATUS_CHOICES:
            self.assertEqual(models.JobStatus.to_str(i[0]), i[1])
        for i in models.JobStatus.SHORT_CHOICES:
            self.assertEqual(models.JobStatus.to_slug(i[0]), i[1])

    def test_osversion(self):
        os, created = models.OSVersion.objects.get_or_create(name="os", version="1")
        self.assertIn("os", os.__unicode__())
        self.assertIn("1", os.__unicode__())

    def test_loadedmodule(self):
        mod, created = models.LoadedModule.objects.get_or_create(name="module")
        self.assertIn("module", mod.__unicode__())

    def test_humanize_bytes(self):
        self.assertEqual(models.humanize_bytes(10), "10.0 B")
        self.assertEqual(models.humanize_bytes(2*1024), "2.0 KiB")
        self.assertEqual(models.humanize_bytes(math.pow(1024, 8)), "1.0 YiB")

    def test_jobTestStatistics(self):
        job = utils.create_job()
        stats, created = models.JobTestStatistics.objects.get_or_create(job=job, passed=1, failed=2, skipped=3)
        s = stats.__unicode__()
        self.assertIn("1 passed", s)
        self.assertIn("2 failed", s)
        self.assertIn("3 skipped", s)

    def test_gitevent(self):
        ge = utils.create_git_event()
        s = ge.__unicode__()
        self.assertIn("Success", s)
        self.assertIn("foo", ge.dump())
        ge.success = False
        ge.body = ""
        ge.save()
        s = ge.__unicode__()
        self.assertIn("Error", s)
        self.assertEqual("", ge.dump())
