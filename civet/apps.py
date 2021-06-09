from django.apps import AppConfig

import time, threading
from croniter import croniter
from datetime import datetime, timedelta
import os
from django.shortcuts import get_object_or_404
from django.conf import settings
from django.core.management import call_command
import logging

logger = logging.getLogger('ci')

class scheduleConfig(AppConfig):
    name = "test"

    def schedulePinger():
        last_run_times = {}
        interval = croniter("*/1 * * * *", datetime.now()) #used to make the program sleeps until every *nth* minute, not every n minutes (12:00, 12:05, 12:10, rather than 12:01, 12:06, 12:11)

        from ci import models, ManualEvent #has to be done here, because these parts of the django app aren't initialized until ready() runs

        logger.info("scheduler is starting")
        while(True):
            logger.info("SCHEDULER: checking for scheduled recipes")
            #get all recipes with schedules, to check if recipes have been changed/added since the last load
            dbRecipes = models.Recipe.objects.filter(active=True, current=True, scheduler__isnull=False, branch__isnull=False).exclude(scheduler="") #get only objects with schedules
            now = datetime.now()

            for r in dbRecipes:
                logger.info("SCHEDULER:     Checking recipe " + r.name)
                if r.id not in last_run_times:
                    last_run_times[r.id] = datetime.fromtimestamp(0)
                last_run = last_run_times[r.id]
                c = croniter(r.scheduler, start_time=last_run + timedelta(seconds=1))
                next_run_time = c.get_next(datetime)

                if next_run_time <= now:
                    user = r.build_user
                    branch = r.branch
                    latest = user.api().last_sha(branch.repository.user.name, branch.repository.name, branch.name)
                    if latest: #likely need to add exception checks for this!
                        last_run_times[r.id] = now
                        logger.info("SCHEDULER:         job " + r.name + ", soonest run time is {}".format(next_run_time))
                        logger.info("SCHEDULER:         Firing job " + r.name + ", time is " +datetime.now().strftime("%c"))
                        mev = ManualEvent.ManualEvent(user, branch, latest, "", recipe=r)
                        mev.force = True #forces the event through even if it exists. this is because it won't rerun the same job.
                        mev.save(update_branch_status=True) #magically add the job through a blackbox
                        logger.info("SCHEDULER:         Job: " + r.name + " scheduled next for {}".format(c.get_next(datetime)))

            # Sleep for n minutes
            #dt = (interval.get_next(datetime)-datetime.now()).total_seconds()
            dt = 10
            time.sleep(dt)

    def ready(self):
        if os.environ.get('RUN_MAIN', None) != 'true': #prevents the scheduler from running twice, django runs TWO instances of apps by default
            try:
                import uwsgi
                if uwsgi.worker_id() == 1:
                    threading.Thread(target=scheduleConfig.schedulePinger, args=(), daemon=True).start()
            except ImportError:
                pass

