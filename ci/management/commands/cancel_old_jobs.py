from __future__ import unicode_literals, absolute_import
from django.core.management.base import BaseCommand, CommandError
from ci import models, views, TimeUtils
from ci.client import UpdateRemoteStatus
from datetime import timedelta
from django.db.models import Q

class Command(BaseCommand):
    help = 'Cancel old Civet jobs. When a specific civet client is no longer running, ' \
            'it can leave jobs lying around that other clients have to ignore.'
    def add_arguments(self, parser):
        parser.add_argument('--dryrun', default=False, action='store_true',
                help="Don't make any changes, just report what would have happened")
        parser.add_argument('--allowed-fail', default=False, action='store_true',
                help="Instead of cancelling jobs, make old jobs allowed to fail")
        parser.add_argument('--client-runner-user', type=str,
                help="Limit jobs to a particular user. Format: <gitserver name>:<username>")
        group = parser.add_mutually_exclusive_group(required=True)
        group.add_argument('--days', type=int, help="Cancel jobs older than this many days")
        group.add_argument('--hours', type=int, help="Cancel jobs older than this many hours")
        group.add_argument('--minutes', type=int, help="Cancel jobs older than this many minutes")

    def handle(self, *args, **options):
        dryrun = options["dryrun"]
        days = options["days"]
        hours = options["hours"]
        minutes = options["minutes"]
        allowed_fail = options["allowed_fail"]
        client_runner_user = options["client_runner_user"]

        if days:
            d = TimeUtils.get_local_time() - timedelta(days=days)
        elif minutes:
            d = TimeUtils.get_local_time() - timedelta(minutes=minutes)
        elif hours:
            d = TimeUtils.get_local_time() - timedelta(hours=hours)

        jobs = models.Job.objects.filter(active=True, ready=True, status=models.JobStatus.NOT_STARTED, created__lt=d)
        if client_runner_user:
            if ":" not in client_runner_user:
                raise CommandError("Invalid format for username: %s" % client_runner_user)
            host, username = client_runner_user.split(":")
            git_server = models.GitServer.objects.get(name=host)
            git_user = models.GitUser.objects.get(name=username, server=git_server)
            jobs = jobs.filter((Q(recipe__client_runner_user=None) & Q(recipe__build_user__build_key=git_user.build_key)) |
                    Q(recipe__client_runner_user__build_key=git_user.build_key))

        count = jobs.count()
        prefix = ""
        if dryrun:
            prefix = "DRY RUN: "

        if allowed_fail:
            err_msg = "Set to allowed to fail due to civet client not running this job in too long a time"
            status = models.JobStatus.FAILED_OK
            msg = "Job allowed to fail"
        else:
            err_msg = "Canceled due to civet client not running this job in too long a time"
            status = models.JobStatus.CANCELED
            msg = "Job canceled"

        for job in jobs.all():
            self.stdout.write("%s%s: %s: %s: %s" % (prefix, msg, job.pk, job, job.created))
            if not dryrun:
                views.set_job_canceled(job, err_msg, status)
                UpdateRemoteStatus.job_complete(job)
                job.event.set_complete_if_done()
        if count == 0:
            self.stdout.write("No jobs to cancel")
