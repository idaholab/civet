
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

from django.core.management.base import BaseCommand
from ci.recipe import RecipeCreator
from django.conf import settings
from ci import models
import sys
import traceback

class Command(BaseCommand):
    help = 'Load recipes from RECIPE_BASE_DIR into the DB'
    def add_arguments(self, parser):
        parser.add_argument('--force', default=False, action='store_true', help='Force reloading the recipes'),
        parser.add_argument('--dryrun', default=False, action='store_true', help='Just show what recipes would have changed'),
        parser.add_argument('--recipes', default=settings.RECIPE_BASE_DIR, dest='recipes', help='Recipes directory'),

    def handle(self, *args, **options):
        force = options.get('force')
        dryrun = options.get('dryrun')
        rcreator = RecipeCreator.RecipeCreator(options.get('recipes'))

        try:
            removed, new, changed = rcreator.load_recipes(force, dryrun)
            rcreator.install_webhooks()
            self.stdout.write("\nRecipes: %s deactivated, %s created, %s changed\n\n" % (removed, new, changed))
        except Exception as e:
            self.stderr.write("Failed to load recipes: %s" % traceback.format_exc(e))
            sys.exit(1)
