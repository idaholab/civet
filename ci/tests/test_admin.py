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
from django.test import TestCase
from django.test import override_settings
from ci import models
from ci.tests import utils


@override_settings(INSTALLED_GITSERVERS=[utils.github_config()])
class Tests(TestCase):
    def model_admin(self, model):
        return admin.site._registry[model]

    def test_recipe_display(self):
        recipe = utils.create_recipe()
        display = self.model_admin(models.Recipe).recipe_display(recipe)
        self.assertEqual(display, "%s : %s" % (recipe.filename, recipe.cause_str()))

    def test_recipe_environment_display(self):
        env = utils.create_recipe_environment()
        display = self.model_admin(models.RecipeEnvironment).env_display(env)
        self.assertEqual(
            display, "%s : %s=%s" % (env.recipe.filename, env.name, env.value)
        )

    def test_prestep_display(self):
        prestep = utils.create_prestepsource()
        display = self.model_admin(models.PreStepSource).prestep_display(prestep)
        self.assertEqual(
            display,
            "%s : %s: %s"
            % (prestep.recipe.filename, prestep.recipe.cause_str(), prestep.filename),
        )

    def test_step_display(self):
        step = utils.create_step()
        display = self.model_admin(models.Step).step_display(step)
        self.assertEqual(
            display, "%s : %s : %s" % (step.recipe.filename, step.name, step.filename)
        )

    def test_step_environment_display(self):
        env = utils.create_step_environment()
        display = self.model_admin(models.StepEnvironment).env_display(env)
        self.assertEqual(
            display,
            "%s : %s: %s=%s"
            % (env.step.recipe.filename, env.step.name, env.name, env.value),
        )

    def test_step_result_display(self):
        result = utils.create_step_result()
        display = self.model_admin(models.StepResult).result_display(result)
        self.assertEqual(
            display,
            "%s: %s : %s" % (result.job.recipe.filename, result.job.pk, result.name),
        )
