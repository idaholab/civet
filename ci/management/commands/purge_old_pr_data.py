from __future__ import unicode_literals, absolute_import
from django.core.management.base import BaseCommand, CommandError
from ci import models, TimeUtils
from datetime import timedelta

PURGED_OUTPUT = "The output of this step has been purged due to its age."


class Command(BaseCommand):
    help = (
        "Purge old pull request data. Replaces the step output of pull request jobs "
        "that have not been modified in the given number of days, and removes the "
        "stored JSON payload of pull request events whose jobs are all that old. "
        "The jobs and events themselves are kept."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dryrun",
            default=False,
            action="store_true",
            help="Don't make any changes, just report what would have happened",
        )
        parser.add_argument(
            "--days",
            type=int,
            default=30,
            help="Purge data for jobs not modified in this many days (default: 30)",
        )
        parser.add_argument(
            "--batch-size",
            type=int,
            default=1000,
            help="Number of rows to update at a time (default: 1000)",
        )

    def handle(self, *args, **options):
        dryrun = options["dryrun"]
        days = options["days"]
        batch_size = options["batch_size"]
        if days < 1:
            raise CommandError("--days must be at least 1")
        if batch_size < 1:
            raise CommandError("--batch-size must be at least 1")

        cutoff = TimeUtils.get_local_time() - timedelta(days=days)

        # Job.last_modified is bumped on every save (creation, step updates,
        # completion, invalidation, cancellation), so it is the last activity
        results = (
            models.StepResult.objects.filter(
                job__event__cause=models.Event.PULL_REQUEST,
                job__last_modified__lt=cutoff,
            )
            .exclude(output="")
            .exclude(output=PURGED_OUTPUT)
        )
        # Only remove the payload once every job on the event is old
        events = (
            models.Event.objects.filter(
                cause=models.Event.PULL_REQUEST, last_modified__lt=cutoff
            )
            .exclude(jobs__last_modified__gte=cutoff)
            .exclude(json_data="")
        )

        prefix = ""
        if dryrun:
            prefix = "DRY RUN: "
            num_results = results.count()
            num_events = events.count()
        else:
            # update() doesn't touch the auto_now fields, so purged rows keep
            # their last modified time
            num_results = self.update_in_batches(
                results, batch_size, output=PURGED_OUTPUT
            )
            num_events = self.update_in_batches(events, batch_size, json_data="")

        self.stdout.write(
            "%sPurged output of %s step results from pull request jobs not modified since %s"
            % (prefix, num_results, cutoff)
        )
        self.stdout.write(
            "%sPurged JSON data of %s pull request events" % (prefix, num_events)
        )

    def update_in_batches(self, qs, batch_size, **values):
        """
        Updates the rows in qs batch_size rows at a time to avoid one huge
        transaction. Every value being set must remove the row from qs, otherwise
        this would never finish.
        """
        total = 0
        while True:
            pks = list(qs.order_by().values_list("pk", flat=True)[:batch_size])
            if not pks:
                return total
            total += qs.model.objects.filter(pk__in=pks).update(**values)
