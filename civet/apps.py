from django.apps import AppConfig

import time, threading
from croniter import croniter
from datetime import datetime, timedelta
import os
import logging
import pytz

logger = logging.getLogger('ci')

class scheduleConfig(AppConfig):
    name = "test"

    def schedulePinger():
        logger.debug("SCHEDULER: Starting")

        # Has to be done here, because these parts of the django app aren't initialized until ready() runs
        from ci import models, ManualEvent

        # Used to make the program sleeps until every *nth* minute, not every n minutes
        # (12:00, 12:05, 12:10, rather than 12:01, 12:06, 12:11). Sleep until it is time to run
        interval = croniter("*/5 * * * *", datetime.now())

        # Formats time to something more suitable for logs (no time zone or ms
        format_time = lambda t : t.strftime("%Y-%m-%d %H:%M:%S")
        local_tz = pytz.timezone("US/Mountain")

        while True:
            logger.debug("SCHEDULER: Checking for scheduled recipes")
            # Get all recipes with schedules, to check if recipes have been changed/added since the last load
            dbRecipes = models.Recipe.objects.filter(active=True, current=True, scheduler__isnull=False, branch__isnull=False).exclude(scheduler="")
            now = datetime.now(tz=pytz.UTC)

            for r in dbRecipes:
                logger.debug("SCHEDULER: Checking recipe {}".format(r.name))
                if r.last_scheduled == datetime.fromtimestamp(0, tz=pytz.UTC) and not r.schedule_initial_run:
                    r.last_scheduled = now - timedelta(seconds=1)
                    r.save()

                c = croniter(r.scheduler, start_time=r.last_scheduled.astimezone(local_tz))
                next_job_run_time = c.get_next(datetime)
                user = r.build_user
                branch = r.branch

                if next_job_run_time <= now:
                    latest = user.api().last_sha(branch.repository.user.name, branch.repository.name, branch.name)
                    if latest: #likely need to add exception checks for this!
                        r.last_scheduled = now
                        r.save()
                        logger.info("SCHEDULER: Running scheduled job {} on {}, soonest run time is {}, next run time is {}".format(r.name,
                                                                                                                                    branch.repository.name,
                                                                                                                                    format_time(next_job_run_time),
                                                                                                                                    format_time(c.get_next(datetime))))
                        mev = ManualEvent.ManualEvent(user, branch, latest, "", recipe=r)
                        mev.force = True #forces the event through even if it exists. this is because it won't rerun the same job.
                        mev.save(update_branch_status=True) #magically add the job through a blackbox
                else:
                    logger.debug("SCHEDULER: Not running recipe {} on {}, next run time is {}".format(r.name, branch.repository.name, format_time(next_job_run_time)))

            # Wait until it is time to run
            next_run_time = interval.get_next(datetime)
            dt = (next_run_time - datetime.now()).total_seconds()
            logger.debug("SCHEDULER: Sleeping for {} sec until {}".format(dt, next_run_time))
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
