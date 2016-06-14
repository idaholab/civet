import models
import logging
logger = logging.getLogger('ci')

def job_status(job):
  """
  Figure out what the overall status of a job is.
  This is primarily used when the job is finished.
  While it is running we usually hard code the status.
  Input:
    job: models.Job
  Return:
    models.JobStatus of the job
  """
  status = set()
  for step_result in job.step_results.all():
    status.add(step_result.status)

  if models.JobStatus.RUNNING in status:
    return models.JobStatus.RUNNING
  if models.JobStatus.FAILED in status:
    return models.JobStatus.FAILED
  if models.JobStatus.CANCELED in status:
    return models.JobStatus.CANCELED
  if models.JobStatus.FAILED_OK in status:
    return models.JobStatus.FAILED_OK
  if models.JobStatus.SUCCESS in status:
    return models.JobStatus.SUCCESS
  return models.JobStatus.NOT_STARTED

def event_status(event):
  """
  Figure out what the overall status of an event is.
  Input:
    event: models.Event
  Return:
    a models.JobStatus of the event
  """
  status = set()
  for job in event.jobs.filter(active=True, ready=True).all():
    status.add(job.status)

  if models.JobStatus.RUNNING in status:
    return models.JobStatus.RUNNING
  if models.JobStatus.FAILED in status:
    return models.JobStatus.FAILED
  if models.JobStatus.FAILED_OK in status:
    return models.JobStatus.FAILED_OK
  if models.JobStatus.CANCELED in status:
    return models.JobStatus.CANCELED
  if models.JobStatus.SUCCESS in status:
    return models.JobStatus.SUCCESS
  return models.JobStatus.NOT_STARTED

def cancel_event(ev):
  """
  Cancels all jobs on an event
  Input:
    ev: models.Event
  """
  logger.info('Canceling event {}: {}'.format(ev.pk, ev))
  for job in ev.jobs.all():
    if not job.complete:
      job.status = models.JobStatus.CANCELED
      job.complete = True
      job.save()
      logger.info('Canceling event {}: {} : job {}: {}'.format(ev.pk, ev, job.pk, job))
  ev.complete = True
  ev.status = models.JobStatus.CANCELED
  ev.save()

def make_jobs_ready(event):
  """
  Marks jobs attached to an event as ready to run.

  Jobs are checked to see if dependencies are met and
  if so, then they are marked as ready.
  Input:
    event: models.Event: The event to check jobs for
  """
  completed_jobs = event.jobs.filter(complete=True, active=True)

  if event.jobs.filter(active=True).count() == completed_jobs.count():
    event.complete = True
    event.save()
    logger.info('Event {}: {} complete'.format(event.pk, event))
    return

  for job in event.jobs.filter(active=True, complete=False).prefetch_related('recipe__depends_on').all():
    ready = True
    for dep in job.recipe.depends_on.all():
      q = dep.jobs.filter(event=event)
      num_deps = q.count()
      q = q.filter(complete=True, status__in=[models.JobStatus.FAILED_OK, models.JobStatus.SUCCESS])
      passed_count = q.count()
      if num_deps != passed_count:
        logger.info('job {}: {} does not have depends met'.format(job.pk, job))
        ready = False
        break

    if job.ready != ready:
      job.ready = ready
      job.save()
      logger.info('Job {}: {} : ready: {} : on {}'.format(job.pk, job, job.ready, job.recipe.repository))
