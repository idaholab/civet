from django.contrib.humanize.templatetags.humanize import naturaltime
from django.utils import timezone
import datetime, math

def sortable_time_str(d):
  return d.strftime('%Y%m%d%H%M%S')

def display_time_str(d):
  #return d.strftime('%H:%M:%S %m/%d/%y')
  return naturaltime(d)

def human_time_str(d):
  #return d.strftime('%H:%M:%S %m/%d/%y')
  return naturaltime(d)

def get_local_timestamp():
  return math.floor((timezone.localtime(timezone.now()) - timezone.make_aware(datetime.datetime.fromtimestamp(0))).total_seconds())

def std_time_str(d):
  return d.strftime('%H:%M:%S %m/%d/%y')
