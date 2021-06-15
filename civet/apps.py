from django.apps import AppConfig

import time, threading
from croniter import croniter
from datetime import datetime, timedelta
import os
import logging

logger = logging.getLogger('ci')

class scheduleConfig(AppConfig):
    name = "test"

    def schedulePinger():
        # Used to make the program sleeps until every *nth* minute, not every n minutes
        # (12:00, 12:05, 12:10, rather than 12:01, 12:06, 12:11)
        interval = croniter("*/5 * * * *", datetime.now())

        # Has to be done here, because these parts of the django app aren't initialized until ready() runs
        from ci import models, ManualEvent

        logger.info("scheduler is starting")
        while(True):
            logger.info("SCHEDULER: checking for scheduled recipes")
            # Get all recipes with schedules, to check if recipes have been changed/added since the last load
            dbRecipes = models.Recipe.objects.filter(active=True, current=True, scheduler__isnull=False, branch__isnull=False).exclude(scheduler="")
            now = datetime.now()

            for r in dbRecipes:
                logger.info("SCHEDULER:     Checking recipe " + r.name)
                if r.last_scheduled == datetime.fromtimestamp(0) and not r.schedule_initial_run:
                    r.last_scheduled = now
                    r.save()
                last_run = r.last_scheduled

                c = croniter(r.scheduler, start_time=last_run + timedelta(seconds=1))
                next_run_time = c.get_next(datetime)

                if next_run_time.replace(tzinfo=None) <= now.replace(tzinfo=None):
                    user = r.build_user
                    branch = r.branch
                    latest = user.api().last_sha(branch.repository.user.name, branch.repository.name, branch.name)
                    if latest: #likely need to add exception checks for this!
                        r.last_scheduled = now
                        r.save()
                        logger.info("SCHEDULER:         job " + r.name + ", soonest run time is {}".format(next_run_time))
                        logger.info("SCHEDULER:         Firing job " + r.name + ", time is " +datetime.now().strftime("%c"))
                        mev = ManualEvent.ManualEvent(user, branch, latest, "", recipe=r)
                        mev.force = True #forces the event through even if it exists. this is because it won't rerun the same job.
                        mev.save(update_branch_status=True) #magically add the job through a blackbox
                        logger.info("SCHEDULER:         Job: " + r.name + " scheduled next for {}".format(c.get_next(datetime)))

            # Sleep for n minutes
            dt = interval
            time.sleep(dt)

    def ready(self):
        # Prevents the scheduler from running twice, django runs TWO instances of apps by default
        if os.environ.get('RUN_MAIN', None) != 'true':
            try:
                import uwsgi
                if uwsgi.worker_id() == 1:
                    threading.Thread(target=scheduleConfig.schedulePinger, args=(), daemon=True).start()
            except ImportError:
                pass
