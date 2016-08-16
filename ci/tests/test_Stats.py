import DBTester
from ci.tests import utils
from django.core.urlresolvers import reverse
from ci import Stats
from ci import models

class Tests(DBTester.DBTester):
  def test_set_passed(self):
    result = utils.create_step_result()
    result.save()
    context = {}
    p = Stats.set_passed("%Y-%m-%d", 60*60*24*30*6, "day", "Passed tests in last 6 months, by day", context, "month_chart")
    # no models.JobTestStatistics records
    self.assertEqual(p, None)
    self.assertEqual(context, {})

    models.JobTestStatistics.objects.create(job=result.job, passed=20, skipped=30, failed=40)
    p = Stats.set_passed("%Y-%m-%d", 60*60*24*30*6, "day", "Passed tests in last 6 months, by day", context, "month_chart")
    self.assertNotEqual(context, {})
    self.assertEqual(len(p), 2)
    self.assertEqual(p[1][1], 20)
    self.assertIn("month_chart", context)


  def test_num_tests(self):
    result = utils.create_step_result()
    models.JobTestStatistics.objects.create(job=result.job, passed=20, skipped=30, failed=40)
    response = self.client.get(reverse('ci:num_tests'))
    self.assertEqual(response.status_code, 200)
