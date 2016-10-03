
# Copyright 2016 Battelle Energy Alliance, LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import models
from django.core.urlresolvers import reverse
import traceback
import json
import Permissions
import event
import logging
logger = logging.getLogger('ci')

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
    review_comments_url : Url to the review comments
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
    self.review_comments_url = None
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
    logger.info('New pull request event: PR #{} on {} for {}'.format(self.pr_number, base.branch.repository, self.build_user))
    recipes = models.Recipe.objects.filter(
        active=True,
        current=True,
        build_user=self.build_user,
        repository=base.branch.repository,
        cause=models.Recipe.CAUSE_PULL_REQUEST).order_by('-priority', 'display_name').all()

    if not recipes:
      logger.info("No recipes for PRs on {} for {}".format(base.branch.repository, self.build_user))
      return None, None, None

    pr, pr_created = models.PullRequest.objects.get_or_create(
        number=self.pr_number,
        repository=base.branch.repository,
        )
    pr.title = self.title[:110]
    pr.closed = False
    pr.url = self.html_url
    pr.username = self.trigger_user
    pr.review_comments_url = self.review_comments_url
    pr.save()
    pr.repository.active = True
    pr.repository.save()
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
    if not pr.username:
      pr.username = ev.head.user().name
      pr.save()
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
      ev_url = reverse('ci:view_event', args=[ev.pk])
      message = "Canceled due to new PR <a href='%s'>event</a>" % ev_url
      for old_ev in pr.events.exclude(pk=ev.pk).all():
        event.cancel_event(old_ev, message)

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
    if pr.alternate_recipes.count() == 0:
      logger.info("No additional recipes for pull request %s" % pr)
      return
    self._create_jobs(requests, pr, ev, pr.alternate_recipes.all())

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
        active, signed_in_user = Permissions.is_collaborator(server.auth(), request.session, recipe.build_user, recipe.repository, auth_session=oauth_session, user=user)
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
          server.api().pr_job_status_comment(oauth_session, ev.comments_url, comment)

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
      event.make_jobs_ready(ev)
    except Exception as e:
      logger.warning("Error occurred while created jobs for %s: %s: %s" % (pr, ev, traceback.format_exc(e)))
