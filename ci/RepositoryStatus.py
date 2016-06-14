from ci import models, TimeUtils
from django.utils.html import escape
from django.db.models import Prefetch
from django.core.urlresolvers import reverse

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

  repos = repo_q.order_by('name').prefetch_related(
      Prefetch('branches', queryset=branch_q, to_attr='active_branches')
      ).prefetch_related(Prefetch('pull_requests', queryset=pr_q, to_attr='open_prs')
      ).select_related("user__server")

  repos_data = []
  for repo in repos.all():
    branches = []
    for branch in repo.active_branches:
      branches.append({'id': branch.pk,
        'name': branch.name,
        'status': branch.status_slug(),
        'url': reverse('ci:view_branch', args=[branch.pk,]),
        'git_url': repo.user.server.api().branch_html_url(repo.user.name, repo.name, branch.name),
        'last_modified_date': TimeUtils.sortable_time_str(branch.last_modified),
        'last_modified': TimeUtils.std_time_str(branch.last_modified),
        })

    prs = []
    for pr in repo.open_prs:
      prs.append({'id': pr.pk,
        'title': escape(pr.title),
        'number': pr.number,
        'status': pr.status_slug(),
        'user': pr.username,
        'url': reverse('ci:view_pr', args=[pr.pk,]),
        'git_url': repo.user.server.api().pr_html_url(repo.user.name, repo.name, pr.number),
        'last_modified_sort': TimeUtils.sortable_time_str(pr.last_modified),
        'last_modified_date': TimeUtils.std_time_str(pr.last_modified),
        'created': TimeUtils.std_time_str(pr.created),
        })

    if prs or branches:
      repos_data.append({'id': repo.pk,
        'name': repo.name,
        'branches': branches,
        'prs': prs,
        'url': reverse('ci:view_repo', args=[repo.pk,]),
        'git_url': repo.user.server.api().repo_html_url(repo.user.name, repo.name),
        })

  return repos_data
