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

def sort_stats_by_bin(q, bins):
  by_bin = {}
  for j in q.all():
    b = find_group(j.get("job__created"), bins)
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
  by_bin = sort_stats_by_bin(q, bins)

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
