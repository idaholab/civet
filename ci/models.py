
# Copyright 2016-2025 Battelle Energy Alliance, LLC
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

from __future__ import unicode_literals, absolute_import
from django.db import models
from django.conf import settings
from django.urls import reverse
from six import python_2_unicode_compatible
from ci.gitlab import api as gitlab_api
from ci.gitlab import oauth as gitlab_auth
from ci.bitbucket import api as bitbucket_api
from ci.bitbucket import oauth as bitbucket_auth
from ci.github import api as github_api
from ci.github import oauth as github_auth
import random, re
from django.utils import timezone
from datetime import timedelta, datetime
from ci import TimeUtils
import json
import ansi2html
import logging
import pytz
from django.db.models import Sum
logger = logging.getLogger('ci')

class DBException(Exception):
    pass

class JobStatus(object):
    NOT_STARTED = 0
    SUCCESS = 1
    RUNNING = 2
    FAILED = 3
    FAILED_OK = 4
    CANCELED = 5
    ACTIVATION_REQUIRED = 6
    INTERMITTENT_FAILURE = 7
    SKIPPED = 8

    STATUS_CHOICES = ((NOT_STARTED, "Not started"),
        (SUCCESS, "Passed"),
        (RUNNING, "Running"),
        (FAILED, "Failed"),
        (FAILED_OK, "Allowed to fail"),
        (CANCELED, "Canceled by user"),
        (ACTIVATION_REQUIRED, "Requires activation"),
        (INTERMITTENT_FAILURE, "Intermittent Failure"),
        (SKIPPED, "Skipped"),
        )
    SHORT_CHOICES = (
        (NOT_STARTED, "Not_Started"),
        (SUCCESS, 'Passed'),
        (RUNNING, 'Running'),
        (FAILED, 'Failed'),
        (FAILED_OK, 'Failed_OK'),
        (CANCELED, 'Canceled'),
        (ACTIVATION_REQUIRED, 'Activation_Required'),
        (INTERMITTENT_FAILURE, "Intermittent_Failure"),
        (SKIPPED, "Skipped"),
        )

    @staticmethod
    def to_str(status):
        return JobStatus.STATUS_CHOICES[status][1]

    @staticmethod
    def to_slug(status):
        return JobStatus.SHORT_CHOICES[status][1]

@python_2_unicode_compatible
class GitServer(models.Model):
    """
    One of the git servers. The type for one of the main
    servers. The server could be hosted internally though,
    like our private GitLab server.
    """

    SERVER_TYPE = ((settings.GITSERVER_GITHUB, "GitHub"),
        (settings.GITSERVER_GITLAB, "GitLab"),
        (settings.GITSERVER_BITBUCKET, "BitBucket"),
        )
    name = models.CharField(max_length=120, unique=True) # Name of the server, ex github.com
    host_type = models.IntegerField(choices=SERVER_TYPE)

    def __str__(self):
        return self.name

    def server_config(self):
        for s in settings.INSTALLED_GITSERVERS:
            if self.name == s.get("hostname", "") and self.host_type == s.get("type", -1):
                return s
        return {}

    def api(self, access_user=None, token=None):
        s = self.server_config()
        if self.host_type == settings.GITSERVER_GITHUB:
            return github_api.GitHubAPI(s, access_user=access_user, token=token)
        elif self.host_type == settings.GITSERVER_GITLAB:
            return gitlab_api.GitLabAPI(s, access_user=access_user, token=token)
        elif self.host_type == settings.GITSERVER_BITBUCKET:
            return bitbucket_api.BitBucketAPI(s, access_user=access_user, token=token)

    def api_type(self):
        return self.SERVER_TYPE[self.host_type][1]

    def auth(self):
        if self.host_type == settings.GITSERVER_GITHUB:
            return github_auth.GitHubAuth(server=self)
        elif self.host_type == settings.GITSERVER_GITLAB:
            return gitlab_auth.GitLabAuth(server=self)
        elif self.host_type == settings.GITSERVER_BITBUCKET:
            return bitbucket_auth.BitBucketAuth(server=self)

    def icon_class(self):
        s = self.server_config()
        return s.get("icon_class", "")

    def post_event_summary(self):
        s = self.server_config()
        return s.get("post_event_summary", False)

    def post_job_status(self):
        s = self.server_config()
        return s.get("post_job_status", False)

    def signed_in_user(self, session):
        return self.auth().signed_in_user(self, session)

    def get_admins(self):
        return self.server_config().get('admins', [])

def generate_build_key():
    return random.SystemRandom().randint(0, 2000000000)

@python_2_unicode_compatible
class GitUser(models.Model):
    """
    A user that will be signed into the system via
    one of the supported git servers. The username is
    the username on the the server (like GitHub).
    The build_key gets autogenerated and is intented
    to prevent outside users from accessing certain
    endpoints.
    """

    name = models.CharField(max_length=120)
    build_key = models.IntegerField(default=generate_build_key, unique=True)
    server = models.ForeignKey(GitServer, related_name='users', on_delete=models.CASCADE)
    token = models.CharField(max_length=1024, blank=True) # holds json encoded token
    # When loading the home page, only these repos will be shown
    preferred_repos = models.ManyToManyField("Repository", blank=True,
            related_name="users_with_preferences")

    def __str__(self):
        return self.name

    def start_session(self):
        return self.server.auth().start_session_for_user(self)

    def api(self):
        return self.server.api(self)

    def auth(self):
        return self.server.auth()

    def is_admin(self):
        return self.name in self.server.get_admins()

    class Meta:
        unique_together = ['name', 'server']
        ordering = ['name']

@python_2_unicode_compatible
class Repository(models.Model):
    """
    For use in repositories on GitHub, etc. A typical structure is <user>/<repo>.
    where <user> will be a username or organization name.
    """
    name = models.CharField(max_length=120)
    user = models.ForeignKey(GitUser, related_name='repositories', on_delete=models.CASCADE)
    # Whether this repository is an active target for recipes
    # and thus show up on the main dashboard.
    # A non active repository is something like a fork where no
    # recipes act against and don't show up on the main dashboard.
    # that are only sources for recipes.
    active = models.BooleanField(default=False)
    last_modified = models.DateTimeField(auto_now=True)

    def __str__(self):
        return "%s/%s" % (self.user.name, self.name)

    def server(self):
        return self.user.server

    def repo_html_url(self):
        server = self.user.server
        return server.api().repo_html_url(self.user.name, self.name)

    def get_open_prs_from_server(self, access_user):
        return access_user.api().get_open_prs(self.user.name, self.name)

    def server_config(self):
        return self.server().server_config()

    def repo_settings(self):
        repos_settings = self.server_config().get("repository_settings", {})
        if repos_settings:
            return repos_settings.get("%s/%s" % (self.user.name, self.name), {})
        else:
            return {}

    def failed_but_allowed_label(self):
        return self.get_repo_setting("failed_but_allowed_label_name")

    def get_repo_setting(self, name, default=None):
        s = self.repo_settings()
        val = s.get(name, None)
        if val is None:
            config = self.user.server.server_config()
            val = config.get(name, default)
        return val

    def auto_merge_label(self):
        return self.get_repo_setting("auto_merge_label")

    def auto_merge_require_review(self):
        return self.get_repo_setting("auto_merge_require_review", None)

    def auto_merge_enabled(self):
        return self.get_repo_setting("auto_merge_enabled", False)

    def public(self):
        return self.get_repo_setting("public", self.server_config().get('public_default', False))

    class Meta:
        unique_together = ['user', 'name']

@python_2_unicode_compatible
class Branch(models.Model):
    """
    A branch of a repository.
    """
    name = models.CharField(max_length=120)
    repository = models.ForeignKey(Repository, related_name='branches', on_delete=models.CASCADE)
    status = models.IntegerField(choices=JobStatus.STATUS_CHOICES, default=JobStatus.NOT_STARTED)
    last_modified = models.DateTimeField(auto_now=True)

    def __str__(self):
        return "{}:{}".format(str(self.repository), self.name)

    def user(self):
        return self.repository.user

    def server(self):
        return self.repository.user.server

    def status_slug(self):
        return JobStatus.to_slug(self.status)

    def get_branch_setting(self, name, default=None):
        val = self.repository.get_repo_setting("branch_settings", {}).get(self.name, {})
        return val.get(name, default)

    class Meta:
        unique_together = ['name', 'repository']

@python_2_unicode_compatible
class Commit(models.Model):
    """
    A particular commit in the git repository, identified by the hash.
    """
    branch = models.ForeignKey(Branch, related_name='commits', on_delete=models.CASCADE)
    sha = models.CharField(max_length=120)
    ssh_url = models.URLField(blank=True)

    def __str__(self):
        return "{}:{}".format(str(self.branch), self.short_sha())

    class Meta:
        unique_together = ['branch', 'sha']

    def server(self):
        return self.branch.repository.user.server

    def user(self):
        return self.branch.repository.user

    def repo(self):
        return self.branch.repository

    def short_sha(self):
        return self.sha[:7]

    def commit_html_url(self):
        repo = self.repo()
        user = repo.user
        server = user.server
        return server.api().commit_html_url(user.name, repo.name, self.sha)

@python_2_unicode_compatible
class PullRequest(models.Model):
    """
    A pull request that was generated on a forked repository.
    """
    number = models.IntegerField()
    repository = models.ForeignKey(Repository, related_name='pull_requests', on_delete=models.CASCADE)
    title = models.CharField(max_length=120)
    url = models.URLField()
    username = models.CharField(max_length=200, default='', blank=True) # the user who initiated the PR
    closed = models.BooleanField(default=False)
    created = models.DateTimeField(auto_now_add=True)
    status = models.IntegerField(choices=JobStatus.STATUS_CHOICES, default=JobStatus.NOT_STARTED)
    review_comments_url = models.URLField(null=True, blank=True)
    alternate_recipes = models.ManyToManyField("Recipe", blank=True, related_name="pull_requests")
    last_modified = models.DateTimeField(auto_now=True)

    def __str__(self):
        return '#{} : {}'.format(self.number, self.title)

    class Meta:
        get_latest_by = 'last_modified'
        ordering = ['repository', 'number']
        unique_together = ['repository', 'number']

    def status_slug(self):
        return JobStatus.to_slug(self.status)

    def set_status_from_event(self, ev):
        latest_event = Event.objects.filter(pull_request=self).order_by('-created').first()
        if latest_event != ev:
            return
        self.status = ev.status
        self.save()

@python_2_unicode_compatible
class Event(models.Model):
    """
    Represents an event that has happened. For pull request and push, it
    relies on the webhook of the repo server (like GitHub). This function will
    then generate the event. It can also be a manually scheduled event that
    just takes the current status of the branch and creates an Event off of that.
    Jobs will be generated off of this table.
    """
    PULL_REQUEST = 0
    PUSH = 1
    MANUAL = 2
    RELEASE = 3
    CAUSE_CHOICES = ((PULL_REQUEST, 'Pull request'),
        (PUSH, 'Push'),
        (MANUAL, 'Scheduled'),
        (RELEASE, 'Release'),
        )
    description = models.CharField(max_length=200, default='', blank=True)
    # the user who initiated the event
    trigger_user = models.CharField(max_length=200, default='', blank=True)
    #the user associated with the build key
    build_user = models.ForeignKey(GitUser, related_name='events', on_delete=models.CASCADE)
    head = models.ForeignKey(Commit, related_name='event_head', on_delete=models.CASCADE)
    base = models.ForeignKey(Commit, related_name='event_base', on_delete=models.CASCADE)
    status = models.IntegerField(choices=JobStatus.STATUS_CHOICES, default=JobStatus.NOT_STARTED)
    complete = models.BooleanField(default=False)
    cause = models.IntegerField(choices=CAUSE_CHOICES, default=PULL_REQUEST)
    comments_url = models.URLField(null=True, blank=True)
    pull_request = models.ForeignKey(PullRequest, null=True, blank=True, related_name='events',
            on_delete=models.CASCADE)
    duplicates = models.IntegerField(default=0)
    # stores the actual json that gets sent from the server to create this event
    json_data = models.TextField(blank=True)
    changed_files = models.TextField(blank=True)
    update_branch_status = models.BooleanField(default=True) # Ignored for PRs

    last_modified = models.DateTimeField(auto_now=True)
    created = models.DateTimeField(db_index=True, auto_now_add=True)

    def __str__(self):
        return '{} : {}'.format(self.CAUSE_CHOICES[self.cause][1], str(self.head))

    class Meta:
        ordering = ['-created']
        get_latest_by = 'last_modified'
        unique_together = ['build_user', 'head', 'base', 'duplicates']

    def cause_str(self):
        if self.PUSH == self.cause:
            return 'Push {}'.format(self.base.branch.name)

        return self.CAUSE_CHOICES[self.cause][1]

    def is_manual(self):
        return self.MANUAL == self.cause

    def status_slug(self):
        return JobStatus.to_slug(self.status)

    def user(self):
        return self.head.user()

    def set_changed_files(self, file_list):
        self.changed_files = json.dumps(file_list, indent=2)

    def get_changed_files(self):
        if not self.changed_files:
            return []
        changed_files = json.loads(self.changed_files)
        return changed_files

    def set_json_data(self, data):
        self.json_data = json.dumps(data, indent=2)

    def get_json_data(self):
        if not self.json_data:
            return None
        data = json.loads(self.json_data)
        return data

    def get_job_depends_on(self):
        """
        For each job attached to this event, get a list of dependencies.
        Return:
          dict: jobs are keys with a list of jobs as values
        """
        depends_on = {}
        all_jobs = [j for j in self.jobs.all()]
        for j in all_jobs:
            deps = []
            for r in j.recipe.depends_on.all():
                for j2 in all_jobs:
                    if j2 != j and j2.recipe.filename == r.filename:
                        deps.append(j2)
            depends_on[j] = deps
        return depends_on

    def get_unrunnable_jobs(self):
        """
        Get a list of jobs that won't run due to failed dependencies.
        Return:
          list[Job]: jobs that won't run
        """
        wont_run = []
        depends = self.get_job_depends_on()
        # We want to check the whole dependecy chain.
        # So if we have j0 -> j1 -> j2 and j0 fails
        # we want the list to have j1 and j2.
        while True:
            added = False
            for job, deps in depends.items():
                if job in wont_run:
                    continue
                for d in deps:
                    if (d in wont_run or
                            (d.complete and d.status in [JobStatus.FAILED, JobStatus.CANCELED])):
                        wont_run.append(job)
                        added = True
            if not added:
                break
        return wont_run

    @staticmethod
    def sorted_jobs(jobs):
        # Take advantage of python stable sorting
        # This used to be in a cmp() style function but python3 removed it.
        jobs = sorted(jobs, key=lambda obj: obj.pk)
        jobs = sorted(jobs, key=lambda obj: obj.config.name)
        jobs = sorted(jobs, key=lambda obj: obj.recipe.display_name)
        jobs = sorted(jobs, key=lambda obj: obj.recipe.priority, reverse=True)
        return jobs

    def get_sorted_jobs(self):
        """
        Get a list of job groups based on dependencies.
        These will be sorted by priority, then name
        Return:
          list: Each entry is a list of sorted jobs
        """
        job_depends = self.get_job_depends_on()
        added_jobs = set()
        other = []
        job_groups = []

        other = list(job_depends.keys())
        while other:
            new_other = []
            new_group = []
            for job in other:
                deps = set(job_depends.get(job, []))
                if deps.issubset(added_jobs):
                    new_group.append(job)
                else:
                    new_other.append(job)
            if not new_group:
                """
                If we haven't made any progress just stop.
                """
                new_group.extend(other)
                other = []
            else:
                other = new_other
            added_jobs |= set(new_group)
            job_groups.append(self.sorted_jobs(new_group))

        return job_groups

    def check_done(self):
        """
        Check to see if the event is done running jobs
        """
        unrunnable_jobs = self.get_unrunnable_jobs()
        for j in self.jobs.all():
            if not j.complete and j not in unrunnable_jobs:
                return False
        return True

    def set_complete_if_done(self):
        """
        If all the jobs are done, set the
        event to complete and update the status
        """
        ret = self.check_done()
        if ret:
            self.set_complete()
        return ret

    def status_from_jobs(self):
        """
        Get the status of the event
        assuming that the event is
        not done yet.
        """
        status = set()
        for job in self.jobs.all():
            status.add(job.status)

        return incomplete_status(status)

    def set_status(self, status=None):
        """
        Sets the status of the event.
        Also updates the status of any associated
        PR or branch
        """
        if status is None:
            self.status = self.status_from_jobs()
        else:
            self.status = status
        self.save()

        if self.pull_request:
            self.pull_request.set_status_from_event(self)
        elif self.update_branch_status:
            self.base.branch.status = self.status
            self.base.branch.save()

    def set_complete(self):
        """
        Set the event to complete
        and update the status along
        with associated branch of pull request
        """
        self.complete = True
        status = set()
        unrunnable_jobs = self.get_unrunnable_jobs()
        for j in self.jobs.all():
            if j.complete and j not in unrunnable_jobs:
                status.add(j.status)
        self.set_status(complete_status(status))

    def make_jobs_ready(self):
        """
        Marks jobs attached to an event as ready to run.

        Jobs are checked to see if dependencies are met and
        if so, then they are marked as ready.
        """

        if self.check_done():
            self.complete = True
            self.save()
            logger.info('Event {}: {} complete'.format(self.pk, self))
            return

        job_depends = self.get_job_depends_on()
        for job, deps in job_depends.items():
            if job.complete or job.ready or not job.active:
                continue
            ready = True
            for d in deps:
                if not d.complete or d.status not in [JobStatus.FAILED_OK, JobStatus.SUCCESS, JobStatus.INTERMITTENT_FAILURE, JobStatus.SKIPPED]:
                    logger.info('job {}: {} does not have depends met: {}'.format(job.pk, job, d))
                    ready = False
                    break

            if ready:
                job.ready = ready
                job.save()
                logger.info('{}: {}: {} : ready: {} : on {}'.format(job.event,
                    job.pk, job, job.ready, job.recipe.repository))

    def auto_cancel_event_except_current(self):
        return self.base.branch.get_branch_setting("auto_cancel_push_events_except_current", False)

    def auto_uncancel_previous_event(self):
        return self.base.branch.get_branch_setting("auto_uncancel_previous_event", False)

@python_2_unicode_compatible
class BuildConfig(models.Model):
    """
    Different names for build configurations.
    Used by the client to match available jobs to what
    configurations it supports.
    """
    name = models.CharField(max_length=120)

    def __str__(self):
        return self.name

class RecipeRepository(models.Model):
    """
    This just holds the current SHA of the git repo that stores recipes.
    This is intended to be a singleton so any saves will delete any
    other records.
    There is also a convience function to get the single record or create
    it if it doesn't exist.
    """
    sha = models.CharField(max_length=120, blank=True)
    last_modified = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        """
        Delete any other records besides this one since this is a singleton.
        """
        self.__class__.objects.exclude(id=self.id).delete()
        super(RecipeRepository, self).save(*args, **kwargs)

    @classmethod
    def load(cls):
        """
        Convience function to get the singleton record
        """
        try:
            rec = cls.objects.get()
            rec.refresh_from_db()
            return rec
        except cls.DoesNotExist:
            return cls.objects.create(sha="")

@python_2_unicode_compatible
class Recipe(models.Model):
    """
    Holds information about a recipe.
    A recipe is the central mechanism to attach running scripts (jobs) to
    an event.
    """
    MANUAL = 0
    AUTO_FOR_AUTHORIZED = 1
    FULL_AUTO = 2
    AUTO_CHOICES = ((MANUAL, "Scheduled"),
        (AUTO_FOR_AUTHORIZED, "Authorized users"),
        (FULL_AUTO, "Automatic")
        )

    CAUSE_PULL_REQUEST = 0
    CAUSE_PUSH = 1
    CAUSE_MANUAL = 2
    CAUSE_PULL_REQUEST_ALT = 3
    CAUSE_RELEASE = 5
    CAUSE_CHOICES = ((CAUSE_PULL_REQUEST, 'Pull request'),
        (CAUSE_PUSH, 'Push'),
        (CAUSE_MANUAL, 'Scheduled'),
        (CAUSE_PULL_REQUEST_ALT, 'Pull request alternatives'),
        (CAUSE_RELEASE, 'Release'),
        )
    name = models.CharField(max_length=120)
    display_name = models.CharField(max_length=120)
    help_text = models.TextField(blank=True)
    filename = models.CharField(max_length=120, blank=True)
    pr_base_ref_override = models.CharField(max_length=120, blank=True)
    filename_sha = models.CharField(max_length=120, blank=True)
    build_user = models.ForeignKey(GitUser, related_name='recipes', on_delete=models.CASCADE)
    client_runner_user = models.ForeignKey(GitUser, related_name='client_runner_recipes',
            on_delete=models.CASCADE, null=True)
    repository = models.ForeignKey(Repository, related_name='recipes', on_delete=models.CASCADE)
    # for push recipes this is the branch that was pushed onto
    # for PR recipes this is the branch that the PR is against
    branch = models.ForeignKey(Branch, null=True, blank=True, related_name='recipes',
            on_delete=models.CASCADE)
    private = models.BooleanField(default=False)
    # Whether this is the current version of the recipe to use
    current = models.BooleanField(default=False)
    active = models.BooleanField(default=True) # Whether this recipe should be considered on an event
    cause = models.IntegerField(choices=CAUSE_CHOICES, default=CAUSE_PULL_REQUEST)
    build_configs = models.ManyToManyField(BuildConfig)
    auto_authorized = models.ManyToManyField(GitUser, related_name='auto_authorized', blank=True)
    auto_cancel_on_push = models.BooleanField(default=False)
    create_issue_on_fail = models.BooleanField(default=False)
    create_issue_on_fail_message = models.TextField(blank=True, default="")
    # If True, create a new comment on each fail instead of just updating the issue body
    create_issue_on_fail_new_comment = models.BooleanField(default=False)
    # depends_on depend on other recipes which means that it isn't symmetrical
    depends_on = models.ManyToManyField('Recipe', symmetrical=False, blank=True)
    automatic = models.IntegerField(choices=AUTO_CHOICES, default=FULL_AUTO)
    priority = models.PositiveIntegerField(default=0)
    activate_label = models.CharField(max_length=120, blank=True)
    last_modified = models.DateTimeField(auto_now=True)
    created = models.DateTimeField(auto_now_add=True)
    scheduler = models.CharField(max_length=120, null =True)
    last_scheduled = models.DateTimeField(default=datetime.fromtimestamp(0, tz=pytz.UTC))
    schedule_initial_run = models.BooleanField(default=False)

    def __str__(self):
        return self.name

    class Meta:
        get_latest_by = 'last_modified'

    def cause_str(self):
        if self.CAUSE_PUSH == self.cause:
            return 'Push {}'.format(self.branch.name)

        for c in self.CAUSE_CHOICES:
            if c[0] == self.cause:
                return c[1]

    def dependency_str(self):
        return ', '.join([ dep.display_name for dep in self.depends_on.all() ])

    def auto_str(self):
        return self.AUTO_CHOICES[self.automatic][1]

@python_2_unicode_compatible
class RecipeViewableByTeam(models.Model):
    """
    A team name that can view a job
    """
    recipe = models.ForeignKey(Recipe, related_name='viewable_by_teams', on_delete=models.CASCADE)
    team = models.CharField(max_length=120)
    git_id = models.IntegerField(default=0) # The ID for use with the Git API

    def __str__(self):
        return self.team

    class Meta:
        unique_together = ['recipe', 'team']

@python_2_unicode_compatible
class RecipeEnvironment(models.Model):
    """
    Name value pairs to be inserted into the environment
    at the recipe level, available to all steps.
    """
    recipe = models.ForeignKey(Recipe, related_name='environment_vars', on_delete=models.CASCADE)
    name = models.CharField(max_length=120)
    value = models.CharField(max_length=512)

    def __str__(self):
        return '{}={}'.format(self.name, self.value)

@python_2_unicode_compatible
class PreStepSource(models.Model):
    """
    Since we use bash to execute our steps, we can just add some
    files to be sourced to import variables, functions, etc, before
    running the step.
    """

    recipe = models.ForeignKey(Recipe, related_name='prestepsources', on_delete=models.CASCADE)
    filename = models.CharField(max_length=120, blank=True)

    def __str__(self):
        return self.filename


@python_2_unicode_compatible
class Step(models.Model):
    """
    A specific step in a recipe. The filename points to a specific script
    that will be executed by the client.
    abort_on_failure: If the test fails and this is true then the job stops and fails.
                      If false then it will continue to the next step.
    allowed_to_fail: If this is true and the step fails then the step is marked as FAILED_OK rather
                      than FAIL
    """
    recipe = models.ForeignKey(Recipe, related_name='steps', on_delete=models.CASCADE)
    name = models.CharField(max_length=120)
    filename = models.CharField(max_length=120)
    position = models.PositiveIntegerField(default=0)
    abort_on_failure = models.BooleanField(default=True)
    allowed_to_fail = models.BooleanField(default=False)

    def __str__(self):
        return self.name

    class Meta:
        ordering = ['position',]

@python_2_unicode_compatible
class StepEnvironment(models.Model):
    """
    Name value pairs to be inserted into the environment
    before running each step. Only available to a step.
    """
    step = models.ForeignKey(Step, related_name='step_environment', on_delete=models.CASCADE)
    name = models.CharField(max_length=120)
    value = models.CharField(max_length=512)

    def __str__(self):
        return '{}:{}'.format(self.name, self.value)

@python_2_unicode_compatible
class Client(models.Model):
    """
    Represents a client that is run on the build servers. Since the
    client polls the web server while it is running or if it is idle,
    we can keep track of its status.
    """
    RUNNING = 0
    IDLE = 1
    DOWN = 2
    STATUS_CHOICES = ((RUNNING, "Running a job"),
        (IDLE, "Looking for work"),
        (DOWN, "Not active")
        )
    STATUS_SLUGS = ((RUNNING, "Running"),
        (IDLE, "Looking"),
        (DOWN, "NotActive")
        )
    name = models.CharField(max_length=120)
    ip = models.GenericIPAddressField()
    status = models.IntegerField(choices=STATUS_CHOICES, default=DOWN)
    status_message = models.CharField(max_length=120, blank=True)
    last_seen = models.DateTimeField(auto_now=True)
    created = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

    def status_str(self):
        return self.STATUS_CHOICES[self.status][1]

    def status_slug(self):
        return self.STATUS_SLUGS[self.status][1]

    def unseen_seconds(self):
        return (timezone.make_aware(datetime.utcnow()) - self.last_seen).total_seconds()

    class Meta:
        get_latest_by = 'last_seen'

@python_2_unicode_compatible
class OSVersion(models.Model):
    """
    The name and version of the operating system while a job is running.
    """
    name = models.CharField(max_length=120)
    version = models.CharField(max_length=120)
    other = models.CharField(max_length=120, blank=True)
    created = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return "%s %s" % (self.name, self.version)

@python_2_unicode_compatible
class LoadedModule(models.Model):
    """
    A module loaded while a job is running
    """
    name = models.CharField(max_length=120)
    created = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

def humanize_bytes(num):
    for unit in ['', 'Ki', 'Mi', 'Gi', 'Ti', 'Pi', 'Ei', 'Zi']:
        if abs(num) < 1024.0:
            return "%3.1f %sB" % (num, unit)
        num /= 1024.0
    return "%.1f YiB" % num

@python_2_unicode_compatible
class Job(models.Model):
    """
    Represents the execution of a single config of a Recipe.
    """
    recipe = models.ForeignKey(Recipe, related_name='jobs', on_delete=models.CASCADE)
    event = models.ForeignKey(Event, related_name='jobs', on_delete=models.CASCADE)
    client = models.ForeignKey(Client, null=True, blank=True, on_delete=models.CASCADE)
    complete = models.BooleanField(default=False)
    invalidated = models.BooleanField(default=False)
    same_client = models.BooleanField(default=False)
    ready = models.BooleanField(default=False) # ready means that the job can go out for execution.
    active = models.BooleanField(default=True)
    config = models.ForeignKey(BuildConfig, related_name='jobs', on_delete=models.CASCADE)
    loaded_modules = models.ManyToManyField(LoadedModule, blank=True)
    operating_system = models.ForeignKey(OSVersion, null=True, blank=True, related_name='jobs',
            on_delete=models.CASCADE)
    status = models.IntegerField(choices=JobStatus.STATUS_CHOICES, default=JobStatus.NOT_STARTED)
    seconds = models.DurationField(default=timedelta)
    # the sha of civet_recipes for the scripts in this job
    recipe_repo_sha = models.CharField(max_length=120, blank=True)
    failed_step = models.CharField(max_length=120, blank=True)
    # Just a cached value of the current running step
    running_step = models.CharField(max_length=120, blank=True)
    last_modified = models.DateTimeField(auto_now=True)
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-last_modified"]
        get_latest_by = 'last_modified'
        unique_together = ['recipe', 'event', 'config']

    def __str__(self):
        return '{}:{}'.format(self.recipe.name, self.config.name)

    def str_with_client(self):
        if self.client:
            return "%s on %s" % (self, self.client)
        else:
            return self.__str__()

    def status_slug(self):
        if not self.active and self.status == JobStatus.NOT_STARTED:
            return JobStatus.to_slug(JobStatus.ACTIVATION_REQUIRED)
        return JobStatus.to_slug(self.status)

    def status_str(self):
        if not self.active and self.status == JobStatus.NOT_STARTED:
            return JobStatus.to_str(JobStatus.ACTIVATION_REQUIRED)
        return JobStatus.to_str(self.status)

    def active_results(self):
        return self.step_results.exclude(status=JobStatus.NOT_STARTED)

    def failed(self):
        return self.status == JobStatus.FAILED or self.status == JobStatus.FAILED_OK

    def failed_result(self):
        if self.failed():
            result = self.step_results.filter(status__in=[JobStatus.FAILED, JobStatus.FAILED_OK]
                    ).order_by('status', 'last_modified').first()
            return result
        return None

    def total_output_size(self):
        total = 0
        for result in self.step_results.all():
            total += len(result.output)
        return humanize_bytes(total)

    def unique_name(self):
        if self.recipe.build_configs.count() > 1:
            return "%s %s" % (self.recipe.display_name, self.config.name)
        else:
            return self.recipe.display_name

    def status_from_steps(self):
        """
        Calculate the job status from the status of
        each step
        """
        status = set()
        for step_result in self.step_results.all():
            status.add(step_result.status)
        return complete_status(status)

    def set_status(self, status=None, calc_event=False):
        """
        Set the status of the job.
        Also update the event status.
        """
        if status is None:
            self.status = self.status_from_steps()
        else:
            self.status = status
        self.save()
        if calc_event:
            self.event.set_status()
        else:
            self.event.set_status(status)

    def set_invalidated(self, message, same_client=False, client=None, check_ready=False):
        logger.info("Invalidating: %s : %s: %s" % (self.str_with_client(), self.pk, message))
        old_recipe = self.recipe
        self.complete = False
        latest_recipe = (Recipe.objects.filter(filename=self.recipe.filename, current=True,
            cause=self.recipe.cause).order_by('-created'))
        if latest_recipe.count():
            self.recipe = latest_recipe.first()
        self.invalidated = True
        self.same_client = same_client
        self.seconds = timedelta(seconds=0)
        if client:
            self.client = client
        elif not same_client:
            self.client = None
        self.active = True
        self.ready = False
        self.step_results.all().delete()
        self.failed_step = ""
        self.running_step = ""
        self.event.complete = False
        self.set_status(JobStatus.NOT_STARTED, calc_event=True) # this will save the job and event
        JobChangeLog.objects.create(job=self, message=message)
        if check_ready:
            self.event.make_jobs_ready()
        if old_recipe.jobs.count() == 0:
            old_recipe.delete()

    def init_pr_status(self):
        """
        Updates the PR status to the "Pending" state
        """
        git_api = self.event.build_user.api()
        git_api.update_status(self.event.base,
                        self.event.head,
                        git_api.PENDING,
                        self.absolute_url(),
                        "Waiting",
                        self.unique_name(),
                        git_api.STATUS_START_RUNNING,
                        )

    def calc_total_time(self):
        total = self.step_results.aggregate(Sum('seconds'))
        return total['seconds__sum']

    def absolute_url(self):
        return "%s%s" % (settings.ABSOLUTE_BASE_URL, reverse('ci:view_job', args=[self.pk]))

    def update_badge(self):
        if self.event.cause not in [Event.PUSH, Event.MANUAL]:
            return

        repo = self.recipe.repository
        badges = repo.get_repo_setting("badges", [])
        for b in badges:
            if b["recipe"] == self.recipe.filename:
                rec, created = RepositoryBadge.objects.get_or_create(repository=repo,
                        filename=self.recipe.filename)
                rec.name = b["name"]
                rec.status = self.status
                rec.url = reverse('ci:view_job', args=[self.pk])
                rec.save()
                break

@python_2_unicode_compatible
class JobTestStatistics(models.Model):
    """
    Number of tests run, failed, passed, skipped for a job.
    """
    job = models.ForeignKey(Job, related_name='test_stats', on_delete=models.CASCADE)
    passed = models.IntegerField(default=0)
    failed = models.IntegerField(default=0)
    skipped = models.IntegerField(default=0)
    created = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return "%s passed, %s failed, %s skipped" % (self.passed, self.failed, self.skipped)

@python_2_unicode_compatible
class JobChangeLog(models.Model):
    """
    Holds information about changes of status to the job.
    This can be activation, invalidation, cancel, etc
    """
    job = models.ForeignKey(Job, related_name="changelog", on_delete=models.CASCADE)
    message = models.TextField() # Should be a short message describing what happened
    notes = models.TextField(blank=True) # Additional information
    created = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        out = "%s - %s" % (self.message, TimeUtils.display_time_str(self.created))
        return out

    class Meta:
        ordering = ['-created',]

def terminalize_output(output):
    # Replace "<,&,>" signs
    output = output.replace("&", "&amp;")
    output = output.replace("<", "&lt;")
    output = output.replace(">", "&gt;")
    output = output.replace("\n", "<br/>")
    '''
       Substitute terminal color codes for CSS tags.
       The bold tag can be a modifier on another tag
       and thus sometimes doesn't have its own
       closing tag. Just ignore it in that case.
    '''
    conv = ansi2html.Ansi2HTMLConverter(escaped=False, scheme="xterm")
    return conv.convert(output, full=False)

@python_2_unicode_compatible
class StepResult(models.Model):
    """
    The result of a single step of a Recipe for a single Job.
    """
    job = models.ForeignKey(Job, related_name='step_results', on_delete=models.CASCADE)
    # replicate some of the Step fields because if someone changes
    # the recipe then it wouldn't be represented of the actual
    # results. So these will just be copied over when the result
    # is created.
    # FIXME: This probably is no longer necessary since we create
    # new recipes when they are changed.
    name = models.CharField(max_length=120, blank=True, default='')
    filename = models.CharField(max_length=120, blank=True, default='')
    position = models.PositiveIntegerField(default=0)
    abort_on_failure = models.BooleanField(default=True)
    allowed_to_fail = models.BooleanField(default=False)

    exit_status = models.IntegerField(default=0) # return value of the script
    status = models.IntegerField(choices=JobStatus.STATUS_CHOICES, default=JobStatus.NOT_STARTED)
    complete = models.BooleanField(default=False)
    output = models.TextField(blank=True) # output of the step
    seconds = models.DurationField(default=timedelta) #run time
    last_modified = models.DateTimeField(auto_now=True)

    def __str__(self):
        return '{}:{}'.format(self.job, self.name)

    class Meta:
        unique_together = ['job', 'position']
        ordering = ['position',]

    def status_slug(self):
        return JobStatus.to_slug(self.status)

    def clean_output(self):
        # If the output is over 2Mb then just return a too big message.
        if len(self.output) > (1024*1024*2):
            return "Output too large. You will need to download the results to see this."
        return terminalize_output(self.output)

    def plain_output(self):
        prefix = re.escape("\33[")
        new_out = re.sub(prefix + r"1m", "", self.output)
        new_out = re.sub(prefix + r"(1;)*(\d{1,2})m", "", new_out)
        return new_out

    def output_size(self):
        return humanize_bytes(len(self.output))

def incomplete_status(status):
    """
    Intended for the status of event/PR/branch while
    it is running. This is so that we don't report
    pass/fail until the event is complete.
    Input:
        set[JobStatus]: The set of statuses
    """
    if status == set([JobStatus.NOT_STARTED]):
        return JobStatus.NOT_STARTED
    if status == set([JobStatus.CANCELED]):
        return JobStatus.CANCELED
    if JobStatus.RUNNING in status:
        return JobStatus.RUNNING
    if JobStatus.ACTIVATION_REQUIRED in status:
        return JobStatus.ACTIVATION_REQUIRED
    return JobStatus.RUNNING

def complete_status(status):
    """
    Intended for the status of a completed set of statuses.
    Input:
        set[JobStatus]: The set of statuses
    """
    if status == set([JobStatus.NOT_STARTED]):
        return JobStatus.NOT_STARTED
    if JobStatus.RUNNING in status:
        return JobStatus.RUNNING
    if JobStatus.ACTIVATION_REQUIRED in status:
        return JobStatus.ACTIVATION_REQUIRED
    if JobStatus.FAILED in status:
        return JobStatus.FAILED
    if JobStatus.CANCELED in status:
        return JobStatus.CANCELED
    if JobStatus.INTERMITTENT_FAILURE in status:
        return JobStatus.INTERMITTENT_FAILURE
    if JobStatus.SKIPPED in status:
        return JobStatus.SKIPPED
    if JobStatus.FAILED_OK in status:
        return JobStatus.FAILED_OK
    if JobStatus.SUCCESS in status:
        return JobStatus.SUCCESS
    return JobStatus.NOT_STARTED

@python_2_unicode_compatible
class RepositoryBadge(models.Model):
    """
    Custom badges for a repository as specified in settings.py
    """
    repository = models.ForeignKey(Repository, related_name='badges', on_delete=models.CASCADE)
    filename = models.CharField(max_length=120)
    url = models.URLField(blank=True)
    name = models.CharField(max_length=120)
    status = models.IntegerField(choices=JobStatus.STATUS_CHOICES, default=JobStatus.NOT_STARTED)
    last_modified = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ['repository', 'filename']

    def __str__(self):
        return "%s:%s" % (self.repository, self.name)
