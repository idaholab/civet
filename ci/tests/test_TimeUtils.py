import DBTester
from ci import TimeUtils
import datetime

class Tests(DBTester.DBTester):
  def test_sortable_time_str(self):
    TimeUtils.sortable_time_str(datetime.datetime.now())

  def test_display_time_str(self):
    TimeUtils.display_time_str(datetime.datetime.now())

  def test_human_time_str(self):
    TimeUtils.human_time_str(datetime.datetime.now())

  def test_get_local_timestamp(self):
    TimeUtils.get_local_timestamp()

  def test_std_time_str(self):
    TimeUtils.std_time_str(datetime.datetime.now())
