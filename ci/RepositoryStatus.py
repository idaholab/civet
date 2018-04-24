
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

from __future__ import unicode_literals, absolute_import
from ci import models
from django.db.models import Prefetch
from django.urls import reverse
from django.utils.html import format_html, escape

def main_repos_status(last_modified=None):
    """
    Gets the main page repositories status.
    Input:
      last_modified: DateTime: if records with last_modified are before this they are ignored
    Return:
      list of dicts containing repository information
    """
    repos = models.Repository.objects.filter(active=True)
    return get_repos_status(repos, last_modified)

def filter_repos_status(pks, last_modified=None):
    """
    Utility function to get filter some repositories by pks
    Input:
      pks: list of ints of primary keys of repositories.
      last_modified: DateTime: if records with last_modified are before this they are ignored
    Return:
      list of dicts containing repository information
    """
    repos = models.Repository.objects.filter(pk__in=pks)
    return get_repos_status(repos, last_modified)

def get_repos_status(repo_q, last_modified=None):
    """
    Get a list of open PRs, grouped by repository and sorted by repository name
    Input:
      repo_q: A query on models.Repository
      last_modified: DateTime: if records with last_modified are before this they are ignored
    Return:
      list of dicts containing repository information
    """
    branch_q = models.Branch.objects.exclude(status=models.JobStatus.NOT_STARTED)
    if last_modified is not None:
        branch_q = branch_q.filter(last_modified__gte=last_modified)
        repo_q.filter(last_modified__gte=last_modified)
    branch_q = branch_q.order_by('name')

    pr_q = models.PullRequest.objects.filter(closed=False)
    if last_modified:
        pr_q = pr_q.filter(last_modified__gte=last_modified)
    pr_q = pr_q.order_by('number')

    repos = (repo_q.order_by('name')
                .prefetch_related(Prefetch('branches', queryset=branch_q, to_attr='active_branches'))
                .prefetch_related(Prefetch('pull_requests', queryset=pr_q, to_attr='open_prs'))
                .select_related("user__server"))

    return get_repos_data(repos)

def get_user_repos_with_open_prs_status(username, last_modified=None):
    """
    Get a list of open PRs for a user, grouped by repository and sorted by repository name
    Input:
      user[models.GitUser]: The user to get the status for
    Return:
      list of dicts containing repository information
    """
    pr_q = models.PullRequest.objects.filter(closed=False, username=username).order_by("number")

    if last_modified:
        pr_q = pr_q.filter(last_modified__gte=last_modified)
    repo_q = repos = models.Repository.objects.filter(pull_requests__username=username, pull_requests__closed=False).distinct()
    repos = (repo_q
                .order_by("name")
                .prefetch_related(Prefetch('pull_requests', queryset=pr_q, to_attr='open_prs'))
                .select_related("user__server"))

    return get_repos_data(repos)


def get_repos_data(repos):
    repos_data = []
    for repo in repos.all():
        repo_git_url = repo.repo_html_url()
        repo_url = reverse('ci:view_repo', args=[repo.pk,])
        repo_desc = format_html('<span><a href="{}"><i class="{}"></i></a></span>', repo_git_url, repo.server().icon_class())
        repo_desc += format_html(' <span class="repo_name"><a href="{}">{}</a></span>', repo_url, repo.name)
        branches = []

        if hasattr(repo, "active_branches"):
            for branch in repo.active_branches:
                b_url = reverse('ci:view_branch', args=[branch.pk,])
                b_desc = '<a href="%s">%s</a>' % (b_url, branch.name)

                branches.append({"id": branch.pk, "status": branch.status_slug(), "description": b_desc})

        prs = []
        for pr in repo.open_prs:
            url = reverse('ci:view_pr', args=[pr.pk])
            pr_desc = format_html('<span><a href="{}"><i class="{}"></i></a></span>',
                    pr.url,
                    pr.repository.server().icon_class())
            pr_desc += format_html(' <span class="boxed_job_status_{}" id="pr_status_{}"><a href="{}">#{}</a></span>',
                    pr.status_slug(),
                    pr.pk,
                    url,
                    pr.number)
            pr_desc += ' <span> %s by %s </span>' % (escape(pr.title), pr.username)

            prs.append({'id': pr.pk,
                'description': pr_desc,
                'number': pr.number,
                })

        if prs or branches or repo.active:
            repos_data.append({'id': repo.pk, 'branches': branches, 'description': repo_desc, 'prs': prs })

    return repos_data
