import models
import GitCommitData
import event
import logging
logger = logging.getLogger('ci')

class ManualEvent(object):
  """
  A manual event. This is typically called
  by cron or something similar.
  """
  def __init__(self, build_user, branch, latest):
    """
    Constructor for ManualEvent.
    Input:
      build_user: models.GitUser of the build user
      branch: A models.Branch on which to run the event on.
      latest: str: The latest SHA on the branch
    """
    self.user = build_user
    self.branch = branch
    self.latest = latest
    self.description = ''

  def save(self, request):
    """
    Create the tables in the DB and make any jobs ready.
    Input:
      request: HttpRequest: The request where this originated.
    """
    base_commit = GitCommitData.GitCommitData(
        self.branch.repository.user.name,
        self.branch.repository.name,
        self.branch.name,
        self.latest,
        "",
        self.branch.repository.user.server,
        )
    base = base_commit.create()

    recipes = models.Recipe.objects.filter(active=True, current=True, build_user=self.user, branch=base.branch, cause=models.Recipe.CAUSE_MANUAL).order_by('-priority', 'display_name').all()

    if not recipes:
      logger.info("No recipes for manual on %s for %s" % (base.branch, self.user))
      base_commit.remove()
      return

    self.branch.repository.active = True
    self.branch.repository.save()

    ev, created = models.Event.objects.get_or_create(build_user=self.user, head=base, base=base, cause=models.Event.MANUAL)
    if created:
      ev.complete = False
      ev.description = '(scheduled)'
      ev.save()
      logger.info("Created manual event for %s for %s" % (self.branch, self.user))
    else:
      # This is just an update to the event. We don't want to create new recipes, just
      # use the ones already loaded.
      recipes = []
      for j in ev.jobs.all():
        recipes.append(j.recipe)

    self._process_recipes(ev, recipes)

  def _process_recipes(self, ev, recipes):
    """
    Create jobs based on the recipes.
    Input:
      ev: models.Event
      recipes: Iterable of recipes to process.
    """
    for r in recipes:
      for config in r.build_configs.all():
        job, created = models.Job.objects.get_or_create(recipe=r, event=ev, config=config)
        if created:
          job.ready = False
          job.complete = False
          job.active = r.active
          job.status = models.JobStatus.NOT_STARTED
          job.save()
          logger.info('Created job {}: {} on {}'.format(job.pk, job, r.repository))
    event.make_jobs_ready(ev)
