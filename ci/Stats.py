from django.shortcuts import render
from ci import models, TimeUtils
from graphos.sources.simple import SimpleDataSource
from graphos.renderers.gchart import LineChart
import datetime

def find_group(record, bins):
  prev = bins[0]
  for b in bins[1:]:
    if record > b:
      prev = b
    else:
      return prev
  return bins[-1]

def sort_stats_by_bin(q, key, bins):
  by_bin = {}
  for j in q.all():
    b = find_group(j.get(key), bins)
    js = by_bin.get(b, None)
    if not js:
      by_bin[b] = [j]
    else:
      js.append(j)
  return by_bin

def get_stats_query(since):
  q = models.JobTestStatistics.objects.order_by('job__created')
  if since:
    q = q.filter(job__created__gte=since)
  q = q.values('passed', 'failed', 'skipped', 'job__created')
  return q

def get_stats(since=None, display_format=None, bins=None):
  q = get_stats_query(since)
  by_bin = sort_stats_by_bin(q, "job__created", bins)

  passed_group = []
  skipped_group = []
  failed_group = []
  for key in bins:
    passed = 0
    failed = 0
    skipped = 0
    display = key.strftime(display_format)
    for j in by_bin.get(key, []):
      passed += j.get("passed")
      failed += j.get("failed")
      skipped += j.get("skipped")
    passed_group.append([display, passed])
    failed_group.append([display, failed])
    skipped_group.append([display, skipped])
  return passed_group, failed_group, skipped_group

def set_passed(since, x_axis, title, context, context_key, graph_display, bins):
  p, f, s = get_stats(since, graph_display, bins)
  if p:
    p.insert(0, [x_axis, "passed"])
    options = { "title": title,
        "hAxis": { "title": x_axis },
        "vAxis": { "title": "Number of Tests" },
        }
    context[context_key] = LineChart(SimpleDataSource(data=p), options=options)
    return p

def create_repo_pr_graph(repo, since, x_axis, title, graph_display, bins):
  q = models.PullRequest.objects.filter(repository__pk=repo["id"], created__gte=since).values("created")
  if not q.count():
    return
  data = sort_stats_by_bin(q, "created", bins)
  all_data = [ [x_axis, repo["name"] ] ]
  for key in bins:
    display = key.strftime(graph_display)
    count = len(data.get(key, []))
    row = [display, count]
    all_data.append(row)
  options = { "title": title,
    "hAxis": { "title": x_axis },
    "vAxis": { "title": "%s new PRs" % repo["name"] },
    }
  return LineChart(SimpleDataSource(data=all_data), options=options)

def set_all_repo_prs(repos_q, since, x_axis, title, context, graph_display, bins):
  for repo in repos_q.all():
    graph = create_repo_pr_graph(repo, since, x_axis, title, graph_display, bins)
    if not graph:
      continue
    repos_dict = context.get("repo_graphs", {})
    if not repos_dict:
      context["repo_graphs"] = {}
      repos_dict = context["repo_graphs"]

    graphs = repos_dict.get(repo["id"], [])
    if not graphs:
      repos_dict[repo["id"]] = [graph]
    else:
      graphs.append(graph)

def get_bins(start_date, step):
  bins = [start_date]
  now = TimeUtils.get_local_time().replace(hour=23, minute=59)
  prev = start_date
  while True:
    new = prev + step
    if new < now:
      bins.append(new)
      prev = new
    else:
      break
  return bins

def num_tests(request):
  context = {}

  start = (TimeUtils.get_local_time() - datetime.timedelta(days=180)).replace(hour=0, minute=0)
  bins = get_bins(start, datetime.timedelta(days=7))
  set_passed(start, "week", "Passed tests in last 6 months, by week", context, "month_chart", "%m/%d", bins)

  start = (TimeUtils.get_local_time() - datetime.timedelta(days=7)).replace(hour=0, minute=0)
  bins = get_bins(start, datetime.timedelta(days=1))
  set_passed(start, "day", "Passed tests in last week, by day", context, "week_chart", "%m/%d", bins)
  return render(request, 'ci/num_tests.html', context)

def num_prs_by_repo(request):
  context = {}
  repos_q = models.Repository.objects.filter(active=True).order_by("name").values("id", "name").all()
  repo_map = { v.get("id"): v.get("name") for v in repos_q }

  start = (TimeUtils.get_local_time() - datetime.timedelta(days=180)).replace(hour=0, minute=0)
  bins = get_bins(start, datetime.timedelta(days=7))
  set_all_repo_prs(repos_q, start, "week", "Number of new PRs in last 6 months, by week", context, "%m/%d", bins)

  start = (TimeUtils.get_local_time() - datetime.timedelta(days=7)).replace(hour=0, minute=0)
  bins = get_bins(start, datetime.timedelta(days=1))
  set_all_repo_prs(repos_q, start, "day", "Number of new PRs in last week, by day", context, "%m/%d", bins)

  sorted_repos_by_name = sorted(repo_map.keys(), key=lambda v: repo_map[v].lower())
  repo_data = []
  for key in sorted_repos_by_name:
    repo_graphs = context.get("repo_graphs", {}).get(key, [])
    if repo_graphs:
      repo_data.append({"id": key, "name": repo_map[key], "graphs": repo_graphs})

  context["repos"] = repo_data
  return render(request, 'ci/num_prs.html', context)
