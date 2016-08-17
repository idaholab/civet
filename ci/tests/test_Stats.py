import DBTester
from ci.tests import utils
from django.core.urlresolvers import reverse
from ci import Stats, TimeUtils
from ci import models
import datetime

class Tests(DBTester.DBTester):
  def test_set_passed(self):
    result = utils.create_step_result()
    result.save()
    context = {}
    start = (TimeUtils.get_local_time() - datetime.timedelta(days=1)).replace(hour=0, minute=0)
    bins = Stats.get_bins(start, datetime.timedelta(days=1))
    p = Stats.set_passed(start, "day", "Passed tests in last 6 months, by day", context, "month_chart", "%m/%d", bins)
    # no models.JobTestStatistics records
    for j in p[1:]:
      self.assertEqual(j[1], 0)
    self.assertIn("month_chart", context)

    context = {}
    models.JobTestStatistics.objects.create(job=result.job, passed=20, skipped=30, failed=40)
    p = Stats.set_passed(start, "day", "Passed tests in last 6 months, by day", context, "month_chart", "%m/%d", bins)
    self.assertNotEqual(context, {})
    self.assertEqual(len(p), 3)
    self.assertEqual(p[2][1], 20)
    self.assertIn("month_chart", context)

  def test_num_tests(self):
    result = utils.create_step_result()
    models.JobTestStatistics.objects.create(job=result.job, passed=20, skipped=30, failed=40)
    response = self.client.get(reverse('ci:num_tests'))
    self.assertEqual(response.status_code, 200)
