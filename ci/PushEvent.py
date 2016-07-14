import models
import json
import event
import logging
logger = logging.getLogger('ci')

class PushEvent(object):
  """
  Holds all the data that will go into a Event of
  a Push type. Will create and save the DB tables.
  The creator of this object will need to set the following:
    base_commit : GitCommitData of the base sha
    head_commit : GitCommitData of the head sha
    comments_url : Url to the comments
    full_text : All the payload data
    build_user : GitUser corresponding to the build user
    description : Description of the push, ie "Merge commit blablabla"
  Then calling save() will actually create the tables.
  """
  def __init__(self):
    self.base_commit = None
    self.head_commit = None
    self.comments_url = None
    self.full_text = None
    self.build_user = None
    self.description = ''

  def save(self, request):
    logger.info('New push event on {}/{}'.format(self.base_commit.repo, self.base_commit.ref))
    recipes = models.Recipe.objects.filter(
        active = True,
        current = True,
        branch__repository__user__server = self.base_commit.server,
        branch__repository__user__name = self.base_commit.owner,
        branch__repository__name = self.base_commit.repo,
        branch__name = self.base_commit.ref,
        build_user = self.build_user,
        cause = models.Recipe.CAUSE_PUSH).order_by('-priority', 'display_name').all()
    if not recipes:
      logger.info('No recipes for push on {}/{}'.format(self.base_commit.repo, self.base_commit.ref))
      return

    # create this after so we don't create unnecessary commits
    base = self.base_commit.create()
    head = self.head_commit.create()

    base.branch.repository.active = True
    base.branch.repository.save()

    ev, created = models.Event.objects.get_or_create(
        build_user=self.build_user,
        head=head,
        base=base,
        cause=models.Event.PUSH,
        )
    if not created:
      # This is just an update to the event. We don't want to create new recipes, just
      # use the ones already loaded.
      recipes = []
      for j in ev.jobs.all():
        recipes.append(j.recipe)

    ev.comments_url = self.comments_url
    ev.json_data = json.dumps(self.full_text, indent=2)
    ev.description = self.description
    ev.save()
    self._process_recipes(ev, recipes)

  def _process_recipes(self, ev, recipes):
    for r in recipes:
      if not r.active:
        continue
      for config in r.build_configs.all():
        job, created = models.Job.objects.get_or_create(recipe=r, event=ev, config=config)
        if created:
          job.active = True
          if r.automatic == models.Recipe.MANUAL:
            job.active = False
          job.ready = False
          job.complete = False
          job.save()
          logger.info('Created job {}: {}: on {}'.format(job.pk, job, r.repository))
    event.make_jobs_ready(ev)
