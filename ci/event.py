import models
import logging
from django.core.urlresolvers import reverse
from django.conf import settings
logger = logging.getLogger('ci')
from recipe import RecipeCreator
import traceback
import json
import Permissions

class GitCommitData(object):
  """
  Creates or gets the required DB tables for a
  GitCommit
  """

  def __init__(self, owner, repo, ref, sha, ssh_url, server):
    """
    Constructor.
    Input:
      owner: str: Owner of the repository
      repo: str: Name of the repository
      ref: str: Branch on the repository
      sha: str: SHA of the commit
      ssh_url: str: ssh URL to the repo
      server: models.GitServer: The Git server
    """
    self.owner = owner
    self.server = server
    self.repo = repo
    self.ref = ref
    self.sha = sha
    self.ssh_url = ssh_url
    self.user_created = False
    self.user_record = None
    self.repo_created = False
    self.repo_record = None
    self.branch_created = False
    self.branch_record = None
    self.commit_created = False
    self.commit_record = None

  def create_branch(self):
    """
    Creates up to the branch.
    """
    self.user_record, self.user_created = models.GitUser.objects.get_or_create(name=self.owner, server=self.server)
    if self.user_created:
      logger.info("Created %s user %s:%s" % (self.server.name, self.user_record.name, self.user_record.build_key))

    self.repo_record, self.repo_created = models.Repository.objects.get_or_create(user=self.user_record, name=self.repo)
    if self.repo_created:
      logger.info("Created %s repo %s" % (self.server.name, str(self.repo_record)))

    self.branch_record, self.branch_created = models.Branch.objects.get_or_create(repository=self.repo_record, name=self.ref)
    if self.branch_created:
      logger.info("Created %s branch %s" % (self.server.name, str(self.branch_record)))

  def create(self):
    """
    Will ensure that commit exists in the DB.
    Return:
      The models.Commit that is created.
    """
    self.create_branch()
    self.commit_record, self.commit_created = models.Commit.objects.get_or_create(branch=self.branch_record, sha=self.sha)
    if self.commit_created:
      logger.info("Created %s commit %s" % (self.server.name, str(self.commit_record)))

    if not self.commit_record.ssh_url and self.ssh_url:
      self.commit_record.ssh_url = self.ssh_url
      self.commit_record.save()

    return self.commit_record

  def remove(self):
    """
    After a user calls create(), this will delete the records created.
    """
    if self.commit_record and self.commit_created:
      self.commit_record.delete()
      self.commit_record = None
    if self.branch_record and self.branch_created:
      self.branch_record.delete()
      self.branch_record = None
    if self.repo_record and self.repo_created:
      self.repo_record.delete()
      self.repo_record = None
    if self.user_record and self.user_created:
      self.user_record.delete()
      self.user_record = None

def get_status(status):
  """
  A ordered list of prefered preferences to set.
  If nothing is found in the status set then that
  means it hasn't started.
  Input:
    status: set of models.JobStatus
  Return:
    a model.JobStatus to be used
  """
  if models.JobStatus.FAILED in status:
    return models.JobStatus.FAILED
  if models.JobStatus.CANCELED in status:
    return models.JobStatus.CANCELED
  if models.JobStatus.FAILED_OK in status:
    return models.JobStatus.FAILED_OK
  if models.JobStatus.RUNNING in status:
    return models.JobStatus.RUNNING
  if models.JobStatus.NOT_STARTED in status:
    return models.JobStatus.NOT_STARTED
  if models.JobStatus.SUCCESS in status:
    return models.JobStatus.SUCCESS
  return models.JobStatus.NOT_STARTED

def job_status(job):
  """
  Figure out what the overall status of a job is.
  Input:
    job: models.Job
  Return:
    models.JobStatus of the job
  """
  status = set()
  for step_result in job.step_results.all():
    status.add(step_result.status)

  if models.JobStatus.FAILED in status:
    return models.JobStatus.FAILED
  if models.JobStatus.CANCELED in status:
    return models.JobStatus.CANCELED
  if models.JobStatus.FAILED_OK in status:
    return models.JobStatus.FAILED_OK
  if models.JobStatus.RUNNING in status:
    return models.JobStatus.RUNNING
  if models.JobStatus.NOT_STARTED in status:
    return models.JobStatus.NOT_STARTED
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
  for job in event.jobs.all():
    jstatus = job_status(job)
    status.add(jstatus)

  if models.JobStatus.NOT_STARTED in status:
    return models.JobStatus.NOT_STARTED
  if models.JobStatus.RUNNING in status:
    return models.JobStatus.RUNNING
  if models.JobStatus.FAILED in status:
    return models.JobStatus.FAILED
  if models.JobStatus.FAILED_OK in status:
    return models.JobStatus.FAILED_OK
  if models.JobStatus.SUCCESS in status:
    return models.JobStatus.SUCCESS
  if models.JobStatus.CANCELED in status:
    return models.JobStatus.CANCELED
  return models.JobStatus.NOT_STARTED

  return get_status(status)

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
  status = event_status(event)
  completed_jobs = event.jobs.filter(complete=True)

  if event.jobs.count() == completed_jobs.count():
    event.complete = True
    event.save()
    logger.info('Event {}: {} complete'.format(event.pk, event))
    return

  if status == models.JobStatus.FAILED or status == models.JobStatus.CANCELED:
    # if there is a failed job or it is canceled, don't schedule more jobs
    return

  completed_set = set(completed_jobs)
  for job in event.jobs.filter(active=True).all():
    recipe_deps = job.recipe.dependencies
    ready = True
    for dep in recipe_deps.all():
      recipe_jobs = set(dep.jobs.filter(event=event).all())
      if not recipe_jobs.issubset(completed_set):
        ready = False
        logger.info('job {}: {} does not have depends met'.format(job.pk, job))
        break

    if job.ready != ready:
      job.ready = ready
      job.save()
      logger.info('Job {}: {} : ready: {} : on {}'.format(job.pk, job, job.ready, job.recipe.repository))


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
    creator = RecipeCreator.RecipeCreator(settings.RECIPE_BASE_DIR)
    creator.load_recipes()

    base_commit = GitCommitData(
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
      logger.info("No recipes for manual on %s" % base.branch)
      base_commit.remove()
      return

    ev, created = models.Event.objects.get_or_create(build_user=self.user, head=base, base=base, cause=models.Event.MANUAL)
    if created:
      ev.complete = False
      ev.description = '(scheduled)'
      ev.save()
      logger.info("Created manual event for %s" % self.branch)
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
    make_jobs_ready(ev)

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
    creator = RecipeCreator.RecipeCreator(settings.RECIPE_BASE_DIR)
    creator.load_recipes()

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

    ev, created = models.Event.objects.get_or_create(
        build_user=self.build_user,
        head=head,
        base=base,
        complete=False,
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
    make_jobs_ready(ev)


class PullRequestEvent(object):
  """
  Hold all the data that will go into a Event of
  a Pull Request type. Will create and save the DB tables.
  The creator of this object will need to set the following:
    pr_number: The PR number
    title: The title of the PR
    action: The action that is happening on the PR. One of the corresponding class variables.
    base_commit : GitCommitData of the base sha
    head_commit : GitCommitData of the head sha
    comments_url : Url to the comments
    html_url : Http URL to the repo
    full_text : All the payload data
    build_user : GitUser corresponding to the build user
    trigger_user: Text of user who triggered this PR
    description : Description of the push, ie "Merge commit blablabla"
  """
  OPENED = 0
  CLOSED = 1
  REOPENED = 2
  SYNCHRONIZE = 3

  def __init__(self):
    self.pr_number = None
    self.action = None
    self.build_user = None
    self.base_commit = None
    self.head_commit = None
    self.title = None
    self.html_url = None
    self.full_text = None
    self.comments_url = None
    self.description = ''
    self.trigger_user = ''

  def _already_exists(self, base, head):
    try:
      pr = models.PullRequest.objects.get(
              number=self.pr_number,
              repository=base.branch.repository)
    except models.PullRequest.DoesNotExist:
      return

    if self.action == self.CLOSED and not pr.closed:
      pr.closed = True
      logger.info('Closed pull request {}: #{} on {}'.format(pr.pk, pr, base.branch))
      pr.save()

  def _create_new_pr(self, base, head):
    """
    Creates a new PR from base and head.
    Input:
      base: models.Commit for the base(upstream) repo
      head: models.Commit for the head(development) repo
    """
    logger.info('New pull request event: PR #{} on {}'.format(self.pr_number, base.branch.repository))
    recipes = models.Recipe.objects.filter(
        active=True,
        current=True,
        build_user=self.build_user,
        repository=base.branch.repository,
        cause=models.Recipe.CAUSE_PULL_REQUEST).order_by('-priority', 'display_name').all()

    if not recipes:
      logger.info("No recipes for pull requests on %s" % base.branch.repository)
      return None, None, None

    pr, pr_created = models.PullRequest.objects.get_or_create(
        number=self.pr_number,
        repository=base.branch.repository,
        )
    pr.title = self.title
    pr.closed = False
    pr.url = self.html_url
    pr.save()
    if not pr_created:
      logger.info('Pull request {}: {} already exists'.format(pr.pk, pr))
    else:
      logger.info('Pull request created {}: {}'.format(pr.pk, pr))


    ev, ev_created = models.Event.objects.get_or_create(
        build_user=self.build_user,
        head=head,
        base=base,
        )

    ev.complete = False
    ev.cause = models.Event.PULL_REQUEST
    ev.comments_url = self.comments_url
    ev.description = self.description
    ev.trigger_user = self.trigger_user
    ev.pull_request = pr
    ev.json_data = json.dumps(self.full_text, indent=2)
    ev.save()
    if not ev_created:
      logger.info('Event {}: {} : {} already exists'.format(ev.pk, ev.base, ev.head))
      recipes = []
      for j in ev.jobs.all():
        recipes.append(j.recipe)
    else:
      logger.info('Event created {}: {} : {}'.format(ev.pk, ev.base, ev.head))

    if not pr_created and ev_created:
      # Cancel all the previous events on this pull request
      for old_ev in pr.events.all():
        if ev != old_ev:
          cancel_event(old_ev)

    all_recipes = []
    for r in recipes:
      all_recipes.append(r)
    for r in pr.alternate_recipes.all():
      all_recipes.append(r)

    return pr, ev, all_recipes

  def create_pr_alternates(self, requests, pr):
    """
    Utility function for creating alternate recipes on an existing pr.
    This should not mess with any running jobs but create new jobs if
    they don't already exist.
    This just looks at the latest event on the PR.
    Input:
      request: django.http.HttpRequest
      pr: models.PullRequest that we are processing
    """
    ev = pr.events.latest()
    if not pr.alternate_recipes:
      logger.info("No additional recipes for pull request %s" % pr)
      return
    self._create_jobs(requests, pr, ev, pr.alternate_recipes)

  def _check_recipe(self, request, oauth_session, pr, ev, recipe):
    """
    Check if an individual recipe is active for the PR.
    If it is not then set a comment on the PR saying that they
    need to activate the recipe.
    Input:
      request: django.http.HttpRequest
      oauth_session: requests_oauthlib.OAuth2Session for the build user
      pr: models.PullRequest that we are processing
      ev: models.Event that is attached to this pull request
      recipe: models.Recipe that we need to process
    """
    if not recipe.active:
      return
    active = False
    user = pr.repository.user
    server = user.server
    if recipe.automatic == models.Recipe.FULL_AUTO:
      active = True
    elif recipe.automatic == models.Recipe.MANUAL:
      active = False
    elif recipe.automatic == models.Recipe.AUTO_FOR_AUTHORIZED:
      if user in recipe.auto_authorized.all():
        active = True
      else:
        active, signed_in_user = Permissions.is_collaborator(server.auth(), request.session, recipe.creator, recipe.repository, auth_session=oauth_session, user=user)
      if active:
        logger.info('User {} is allowed to activate recipe: {}: {}'.format(user, recipe.pk, recipe))
      else:
        logger.info('User {} is NOT allowed to activate recipe {}: {}'.format(user, recipe.pk, recipe))

    for config in recipe.build_configs.all():
      job, created = models.Job.objects.get_or_create(recipe=recipe, event=ev, config=config)
      if created:
        job.active = active
        job.ready = False
        job.complete = False
        job.status = models.JobStatus.NOT_STARTED
        job.save()
        logger.info('Created job {}: {}: on {}'.format(job.pk, job, recipe.repository))

        abs_job_url = request.build_absolute_uri(reverse('ci:view_job', args=[job.pk]))
        msg = 'Waiting'
        git_status = server.api().PENDING
        if not active:
          msg = 'Developer needed to activate'
          git_status = server.api().SUCCESS
          comment = 'A build job for {} from recipe {} is waiting for a developer to activate it here: {}'.format(ev.head.sha, recipe.name, abs_job_url)
          server.api().pr_comment(oauth_session, ev.comments_url, comment)

        server.api().update_pr_status(
                oauth_session,
                ev.base,
                ev.head,
                git_status,
                abs_job_url,
                msg,
                str(job),
                )
      else:
        logger.info('Job {}: {}: on {} already exists'.format(job.pk, job, recipe.repository))

  def _process_recipes(self, request, pr, ev, recipes):
    """
    Go through the recipes for this PR. Set the
    status for each recipe. If the recipe isn't
    active then a comment is added telling the
    user to activate it manually.
    Input:
      request: django.http.HttpRequest
      pr: models.PullRequest that we are processing
      ev: models.Event that is attached to this pull request
      recipes: list of models.Recipe that we need to process
    """
    user = ev.build_user
    server = user.server
    oauth_session = server.auth().start_session_for_user(user)
    for r in recipes:
      self._check_recipe(request, oauth_session, pr, ev, r)

  def save(self, requests):
    """
    After the caller has set the variables for base_commit, head_commit, etc, this will actually created the records in the DB
    and get the jobs ready
    Input:
      request: django.http.HttpRequest
    """
    creator = RecipeCreator.RecipeCreator(settings.RECIPE_BASE_DIR)
    creator.load_recipes()

    base = self.base_commit.create()
    head = self.head_commit.create()

    if self.action == self.CLOSED:
      self._already_exists(base, head)
      return

    if self.action in [self.OPENED, self.SYNCHRONIZE, self.REOPENED]:
      pr, ev, recipes = self._create_new_pr(base, head)
      if pr:
        self._create_jobs(requests, pr, ev, recipes)
        return
    # if we get here then we didn't use the commits for anything so they are safe to remove
    self.base_commit.remove()
    self.head_commit.remove()

  def _create_jobs(self, requests, pr, ev, recipes):
    """
    Takes a list of recipes and creates the associated jobs.
    Input:
      request: django.http.HttpRequest
      pr: models.PullRequest that we are processing
      ev: models.Event that is attached to this pull request
      recipes: list of models.Recipe that we need to process
    """
    try:
      self._process_recipes(requests, pr, ev, recipes)
      make_jobs_ready(ev)
    except Exception as e:
      logger.warning("Error occurred while created jobs for %s: %s: %s" % (pr, ev, traceback.format_exc(e)))
