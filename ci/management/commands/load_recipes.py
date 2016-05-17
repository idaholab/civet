from django.core.management.base import BaseCommand
from ci.recipe import RecipeCreator
from django.conf import settings
from ci import models
import sys

class Command(BaseCommand):
  help = 'Load recipes from RECIPES_BASE_DIR into the DB'

  def handle(self, *args, **options):
    rcreator = RecipeCreator.RecipeCreator(settings.RECIPE_BASE_DIR)
    # create the moosebuild and moose test users if they don't exists
    github, created = models.GitServer.objects.get_or_create(host_type=settings.GITSERVER_GITHUB)
    gitlab, created = models.GitServer.objects.get_or_create(host_type=settings.GITSERVER_GITLAB)
    models.GitUser.objects.get_or_create(name="moosebuild", server=github)
    models.GitUser.objects.get_or_create(name="moosetest", server=gitlab)
    try:
      rcreator.load_recipes()
    except Exception as e:
      print("Failed to load recipes: %s" % e)
      sys.exit(1)
