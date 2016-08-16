from django.shortcuts import render
from ci import models, TimeUtils
from graphos.sources.simple import SimpleDataSource
from graphos.renderers.gchart import LineChart
import itertools

def get_stats(str_group, seconds=None):
  q = models.JobTestStatistics.objects.order_by('job__last_modified')
  if seconds:
    dt = TimeUtils.get_datetime_since(seconds)
    q = q.filter(job__last_modified__gte=dt)
  q = q.values('passed', 'failed', 'skipped', 'job__last_modified')
  grouped = itertools.groupby(q.all(), lambda record: record.get('job__last_modified').strftime(str_group))
  passed_group = []
  skipped_group = []
  failed_group = []
  for group, jobs_in_group in grouped:
    passed = 0
    failed = 0
    skipped = 0
    for j in jobs_in_group:
      passed += j.get("passed")
      failed += j.get("failed")
      skipped += j.get("skipped")
    passed_group.append([group, passed])
    failed_group.append([group, failed])
    skipped_group.append([group, skipped])
  return passed_group, failed_group, skipped_group

def set_passed(str_group, seconds, x_axis, title, context, context_key):
  p, f, s = get_stats(str_group, seconds)
  if p:
    p.insert(0, [x_axis, "passed"])
    context[context_key] = LineChart(SimpleDataSource(data=p), options={'title': title})
    return p

def num_tests(request):
  context = {}
  set_passed("%Y-%m-%d", 60*60*24*30*6, "day", "Passed tests in last 6 months, by day", context, "month_chart")
  set_passed("%Y-%m-%d", 60*60*24*7, "day", "Passed tests in last week, by day", context, "week_chart")
  set_passed("%Y-%m-%d-%H", 60*60*24, "hour", "Passed tests in last day, by hour", context, "day_chart")
  return render(request, 'ci/num_tests.html', context)
