from __future__ import unicode_literals, absolute_import
from django.core.management.base import BaseCommand
from ci import models, views, TimeUtils
from datetime import timedelta

class Command(BaseCommand):
    help = 'Cancel old Civet jobs. When a specific civet client is no longer running, it can leave jobs lying around that other clients have to ignore.'
    def add_arguments(self, parser):
        parser.add_argument('--dryrun', default=False, action='store_true', help="Don't make any changes, just report what would have happened")
        parser.add_argument('--days', required=True, type=int, help="Cancel jobs older than this many days")

    def handle(self, *args, **options):
        dryrun = options["dryrun"]
        days = options["days"]
        d = TimeUtils.get_local_time() - timedelta(days=days)

        jobs = models.Job.objects.filter(active=True, ready=True, status=models.JobStatus.NOT_STARTED, created__lt=d)
        count = jobs.count()
        prefix = ""
        if dryrun:
            prefix = "DRY RUN: "

        for job in jobs.all():
            self.stdout.write("%sCancel job %s: %s: %s" % (prefix, job.pk, job, job.created))
            if not dryrun:
                views.set_job_canceled(job, "Civet client hasn't run this job in too long a time")
                job.event.set_complete_if_done()
        if count == 0:
            self.stdout.write("No jobs to cancel")
