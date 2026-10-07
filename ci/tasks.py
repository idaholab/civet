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

"""
Background tasks that update the Git server.

Requests to the Git server (commit statuses, PR comments, labels, etc) can be
slow, so they are enqueued here instead of being made while handling a request.
That way webhooks, clients and users get a response without waiting on them.

The arguments are the primary keys of the records and the values to send, as
they need to be JSON serializable. The tasks that post a single status, comment
or label take the values that were captured when they were enqueued, so that a
task that runs later sends what was true at the time. The tasks for completed
jobs and events build their updates from the records when they run.

The database backend stores a task in the same transaction as the records
that it uses, so the worker can't run it before those records are committed.

The tasks run in the order they were enqueued when there is a single worker,
which keeps the statuses of a job (pending, running, complete) in order.
"""

from __future__ import unicode_literals, absolute_import
from typing import Optional
from django.tasks import task
from ci import models


@task
def update_status(
    event_id: int,
    state: int,
    url: str,
    description: str,
    context: str,
    job_stage: int,
) -> None:
    """
    Updates a commit status on the head of an event. See GitAPI.update_status.
    """
    ev = models.Event.objects.select_related(
        "build_user__server", "base__branch__repository__user", "head"
    ).get(pk=event_id)
    git_api = ev.build_user.api()
    git_api.update_status(ev.base, ev.head, state, url, description, context, job_stage)


@task
def pr_comment(build_user_id: int, url: str, msg: str) -> None:
    """
    Posts a comment on a PR. See GitAPI.pr_comment.
    """
    build_user = models.GitUser.objects.select_related("server").get(pk=build_user_id)
    build_user.api().pr_comment(url, msg)


@task
def add_pr_label(build_user_id: int, repo_id: int, pr_num: int, label: str) -> None:
    """
    Adds a label to a PR. See GitAPI.add_pr_label.
    """
    build_user = models.GitUser.objects.select_related("server").get(pk=build_user_id)
    repo = models.Repository.objects.select_related("user").get(pk=repo_id)
    build_user.api().add_pr_label(repo, pr_num, label)


@task
def remove_pr_label(build_user_id: int, repo_id: int, pr_num: int, label: str) -> None:
    """
    Removes a label from a PR. See GitAPI.remove_pr_label.
    """
    build_user = models.GitUser.objects.select_related("server").get(pk=build_user_id)
    repo = models.Repository.objects.select_related("user").get(pk=repo_id)
    build_user.api().remove_pr_label(repo, pr_num, label)


@task
def remove_pr_todo_labels(
    build_user_id: int,
    owner: str,
    repo: str,
    pr_num: int,
    labels: Optional[list[str]],
) -> None:
    """
    Removes the labels on a PR that need to be removed when it gets new commits.
    Only supported on GitHub. See GitHubAPI._remove_pr_todo_labels.
    """
    build_user = models.GitUser.objects.select_related("server").get(pk=build_user_id)
    build_user.api()._remove_pr_todo_labels(owner, repo, pr_num, labels=labels)


@task
def job_complete_status(job_id: int, do_status_update: bool) -> None:
    """
    Updates the Git server for a job that has completed.
    See UpdateRemoteStatus.job_complete_status.
    """
    from ci.client import UpdateRemoteStatus

    UpdateRemoteStatus.job_complete_status(
        models.Job.objects.get(pk=job_id), do_status_update
    )


@task
def event_complete(event_id: int, do_failed_but_allowed_label: bool) -> None:
    """
    Updates the Git server for an event that has completed.
    See UpdateRemoteStatus.event_complete.
    """
    from ci.client import UpdateRemoteStatus

    UpdateRemoteStatus.event_complete(
        models.Event.objects.get(pk=event_id), do_failed_but_allowed_label
    )


@task
def job_complete_remote(job_id: int, all_done: bool) -> None:
    """
    Updates the Git server for a job that has completed, along with its event
    if all of its jobs are done. See UpdateRemoteStatus.job_complete_remote.
    """
    from ci.client import UpdateRemoteStatus

    UpdateRemoteStatus.job_complete_remote(models.Job.objects.get(pk=job_id), all_done)
