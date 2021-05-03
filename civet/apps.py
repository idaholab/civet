from django.apps import AppConfig

import time, threading
from croniter import croniter
from datetime import datetime
from cron_descriptor import get_description, ExpressionDescriptor
import os
from django.shortcuts import get_object_or_404
from django.conf import settings
from django.core.management import call_command
class scheduleConfig(AppConfig):
	name = "test"

	def schedulePinger():
		crons = []
		fiveMinuter = croniter("*/1 * * * *", datetime.now()) #used to make the program sleeps until every *5TH* minute, not every 5 minutes (12:00, 12:05, 12:10, rather than 12:01, 12:06, 12:11)
		from ci import models, ManualEvent #has to be done here, because these parts of the django app aren't initialized until ready() runs
		#initialize the crons list for the first time
		for recipe in models.Recipe.objects.filter(scheduler__isnull=False, branch__isnull=False).exclude(scheduler=""): #get only objects with schedules
			cron = {}
			#sets each scheduled job in its own dict, stored in the crons array. Used for easier management of data.
			cron['instance'] = croniter(recipe.scheduler, datetime.now())
			cron['nextJob'] = cron['instance'].get_next(datetime)
			cron['recipe'] = recipe
			crons.append(cron)
			#don't know how civet logging works, but should likely add these to it
			print("Instantiated schedule for "+recipe.name)
			print("Running "+get_description(recipe.scheduler)) #prints human readable cron string
			print("Job: " + recipe.name + " scheduled for " + cron['nextJob'].strftime("%c"))

		while(True):
			#Reload recipes. Currently disabled, as I am not sure if it is necessary, as, afaik, civet already does this re: jason. Check with him
			#print("Reloading recipes... Please note this is threaded, and will display a second line after completion")
			#call_command('load_recipes')
			#print("Done reloading recipes")

			#get all recipes with schedules, to check if recipes have been changed/added since the last load
			dbRecipes = models.Recipe.objects.filter(scheduler__isnull=False, branch__isnull=False).exclude(scheduler="") #get only objects with schedules

			#if the current ids in the list don't match the database entries, redo the entire list
			#since the database makes NEW ids for any changed OR new recipes, this makes sure to capture every change to the recipes
			if [c['recipe'].id for c in crons] != [r.id for r in dbRecipes]: #dumb pythonic hack, actually faster than iterating normally too
				print("DB changed - reloading crons\n")
				crons = []
				for recipe in dbRecipes:
					#this code is identical to the initialization
					cron = {}
					#sets each scheduled job in its own dict, stored in the crons array. Used for easier management of data.
					cron['instance'] = croniter(recipe.scheduler, datetime.now())
					cron['nextJob'] = cron['instance'].get_next(datetime)
					cron['recipe'] = recipe
					crons.append(cron)
					#don't know how civet logging works, but should likely add these to it
					print("Instantiated schedule for "+recipe.name)
					print("Running "+get_description(recipe.scheduler)) #prints human readable cron string
					print("Job: " + recipe.name + " scheduled for " + cron['nextJob'].strftime("%c"))


			for c in crons:
				#Next, if the scheduled time of the next job is now, or if it was supposed to have been fired during the last 5min sleep, the job is fired
				if (c['nextJob']-datetime.now()).total_seconds() <= 0:
					print('#####################')
					print("Firing job " + c['recipe'].name + ", time is " +datetime.now().strftime("%c"))
					#Actually run the job
					user = get_object_or_404(models.GitUser, name=recipe.build_user)
					branch = recipe.branch
					latest = user.api().last_sha(branch.repository.user.name, branch.repository.name, branch.name)
					if latest: #likely need to add exception checks for this!
						mev = ManualEvent.ManualEvent(user, branch, latest, "")
						mev.force = True #forces the event through even if it exists. this is because it won't rerun the same job.
						mev.save(update_branch_status=True) #magically add the job through a blackbox

					#Set the time of the next job
					#Note this DOES NOT work properly for schedules < 5min, as the program always sleeps at least that long
					c['nextJob'] = c['instance'].get_next(datetime)
					print("\nJob: " + c['recipe'].name + " scheduled next for " + cron['nextJob'].strftime("%c"))
					print('#####################\n')


			#Sleep for 5 minutes
			sleepTime = (fiveMinuter.get_next(datetime)-datetime.now()).total_seconds()
			time.sleep(sleepTime)

	def ready(self):
		if os.environ.get('RUN_MAIN', None) != 'true': #prevents the scheduler from running twice, django runs TWO instances of apps by default
			print("schedule loaded")
			threading.Thread(target=scheduleConfig.schedulePinger, args=()).start()

			#call_command("load_recipes")
