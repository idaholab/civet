from django.core.management.base import BaseCommand
from ci.client import ParseOutput
from ci import models

class Command(BaseCommand):
  help = 'Set the test stats for all jobs'

  def handle(self, *args, **options):
    for j in models.Job.objects.iterator():
      ParseOutput.set_job_stats(j)
      j.refresh_from_db()
      if j.test_stats.exists():
        print("%s: %s" % (j, j.test_stats.first()))
