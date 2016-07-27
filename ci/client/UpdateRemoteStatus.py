
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

from ci import models
from django.core.urlresolvers import reverse

def add_comment(request, oauth_session, user, job):
  """
  Add a comment to the PR to indicate the status of the job.
  This typically only happens when the job is finished.
  """
  if job.event.cause != models.Event.PULL_REQUEST:
    return
  if not job.event.comments_url:
    return
  comment = 'Testing {}\n\n{} {}: **{}**\n'.format(job.event.head.sha, job.recipe.name, job.config, job.status_str())
  abs_job_url = request.build_absolute_uri(reverse('ci:view_job', args=[job.pk]))
  comment += '\nView the results [here]({}).\n'.format(abs_job_url)
  user.server.api().pr_job_status_comment(oauth_session, job.event.comments_url, comment)

def job_started(request, job):
  """
  Indicates that the job as started.
  This will update the CI status on the Git server.
  """
  if job.event.cause == models.Event.PULL_REQUEST:
    user = job.event.build_user
    oauth_session = user.server.auth().start_session_for_user(user)
    api = user.server.api()
    api.update_pr_status(
        oauth_session,
        job.event.base,
        job.event.head,
        api.PENDING,
        request.build_absolute_uri(reverse('ci:view_job', args=[job.pk])),
        'Starting',
        str(job),
        )

def step_start_pr_status(request, step_result, job):
  """
  This gets called when the client starts a step.
  Just tries to update the status on the server.
  """

  if job.event.cause != models.Event.PULL_REQUEST:
    return

  user = job.event.build_user
  server = user.server
  oauth_session = server.auth().start_session_for_user(user)
  api = server.api()
  status = api.RUNNING
  desc = '({}/{}) {}'.format(step_result.position+1, job.step_results.count(), step_result.name)

  api.update_pr_status(
      oauth_session,
      job.event.base,
      job.event.head,
      status,
      request.build_absolute_uri(reverse('ci:view_job', args=[job.pk])),
      desc,
      str(job),
      )

def job_complete_pr_status(request, job):
  """
  Indicates that the job has completed.
  This will update the CI status on the Git server and
  try to add a comment.
  """
  user = job.event.build_user
  oauth_session = user.server.auth().start_session_for_user(user)
  api = user.server.api()

  if job.event.cause == models.Event.PULL_REQUEST:
    status_dict = { models.JobStatus.FAILED_OK:(api.SUCCESS, "Failed but allowed"),
        models.JobStatus.CANCELED: (api.CANCELED, "Canceled"),
        models.JobStatus.FAILED: (api.FAILURE, "Failed"),
        }
    status, msg = status_dict.get(job.status, (api.SUCCESS, "Passed"))

    api.update_pr_status(
        oauth_session,
        job.event.base,
        job.event.head,
        status,
        request.build_absolute_uri(reverse('ci:view_job', args=[job.pk])),
        msg,
        str(job),
        )
    add_comment(request, oauth_session, user, job)

def step_complete_pr_status(request, step_result, job):
  """
  This gets called when the client completes a step.
  Just tries to update the status on the server.
  This is mainly for updating the description on GitHub
  as the status isn't changed. GitLab doesn't seem
  to use the description anywhere so it probably
  isn't required to do this update but to avoid
  special casing git servers do it anyway.
  """

  if job.event.cause != models.Event.PULL_REQUEST:
    return

  user = job.event.build_user
  server = user.server
  oauth_session = server.auth().start_session_for_user(user)
  api = server.api()
  # Always keep the status as RUNNING, it will get set properly in job_finished.
  # GitLab doesn't seem to like setting FAILURE or CANCELED multiple times as
  # it creates a new "build" for each one.
  status = api.RUNNING

  desc = '(%s/%s) complete' % (step_result.position+1, job.step_results.count())
  if job.status == models.JobStatus.CANCELED:
    desc = 'Canceled'

  if step_result.exit_status != 0 and not step_result.allowed_to_fail:
    desc = '{} exited with code {}'.format(step_result.name, step_result.exit_status)

  api.update_pr_status(
      oauth_session,
      job.event.base,
      job.event.head,
      status,
      request.build_absolute_uri(reverse('ci:view_job', args=[job.pk])),
      desc,
      str(job),
      )
