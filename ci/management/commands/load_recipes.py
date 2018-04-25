
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

from __future__ import unicode_literals
from django.core.management.base import BaseCommand
from ci.recipe import RecipeCreator
from django.conf import settings
import sys
import traceback

class Command(BaseCommand):
    help = 'Load recipes from RECIPE_BASE_DIR into the DB'
    def add_arguments(self, parser):
        parser.add_argument('--force', default=False, action='store_true', help='Force reloading the recipes'),
        parser.add_argument('--dryrun', default=False, action='store_true', help='Just show what recipes would have changed'),
        parser.add_argument('--recipes', default=settings.RECIPE_BASE_DIR, dest='recipes', help='Recipes directory'),
        parser.add_argument('--install-webhooks', default=False, action='store_true', help='Try to install webhooks'),

    def handle(self, *args, **options):
        force = options.get('force')
        dryrun = options.get('dryrun')
        rcreator = RecipeCreator.RecipeCreator(options.get('recipes'))

        try:
            removed, new, changed = rcreator.load_recipes(force, dryrun)
            if options.get("install_webhooks"):
                rcreator.install_webhooks()
            self.stdout.write("\nRecipes: %s deactivated, %s created, %s changed\n\n" % (removed, new, changed))
        except Exception:
            self.stderr.write("Failed to load recipes: %s" % traceback.format_exc())
            sys.exit(1)
