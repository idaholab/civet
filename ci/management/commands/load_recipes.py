from django.core.management.base import BaseCommand
from ci.recipe import RecipeCreator
from django.conf import settings
from ci import models
from optparse import make_option
import sys

class Command(BaseCommand):
  help = 'Load recipes from RECIPE_BASE_DIR into the DB'
  option_list = BaseCommand.option_list + (
      make_option('--force', default=False, action='store_true', dest='force', help='Force reloading the recipes'),
      make_option('--recipes', default=settings.RECIPE_BASE_DIR, dest='recipes', help='Recipes directory'),
      )

  def handle(self, *args, **options):
    if options.get('force'):
      rec = models.RecipeRepository.load()
      rec.sha = ""
      rec.save()
    print("Loading recipes from %s" % options.get("recipes"))
    rcreator = RecipeCreator.RecipeCreator(options.get('recipes'))
    # create the moosebuild and moose test users if they don't exists
    github, created = models.GitServer.objects.get_or_create(host_type=settings.GITSERVER_GITHUB)
    github.name = "github.com"
    github.save()
    gitlab, created = models.GitServer.objects.get_or_create(host_type=settings.GITSERVER_GITLAB)
    gitlab.name = "hpcgitlab.inl.gov"
    gitlab.save()

    models.GitUser.objects.get_or_create(name="moosebuild", server=github)
    models.GitUser.objects.get_or_create(name="moosetest", server=gitlab)
    try:
      num_recipes = models.Recipe.objects.count()
      rcreator.load_recipes()
      new_num_recipes = models.Recipe.objects.count()
      print("Created %s new recipes" % (new_num_recipes - num_recipes))
    except Exception as e:
      print("Failed to load recipes: %s" % e)
      sys.exit(1)
