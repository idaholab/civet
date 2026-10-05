from __future__ import unicode_literals, absolute_import
from django.apps import apps
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q
from ci import models, TimeUtils
from collections import Counter
from datetime import timedelta


class Command(BaseCommand):
    help = (
        "Delete old pull request data. Deletes pull request events (along with "
        "their jobs and step results) whose jobs have not been modified in the "
        "given number of days, except for the latest event on an open pull "
        "request. Closed pull requests without any events and commits that are "
        "no longer used by any event are deleted as well."
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
            help="Delete data for events not modified in this many days (default: 30)",
        )
        parser.add_argument(
            "--batch-size",
            type=int,
            default=100,
            help="Number of events to delete at a time (default: 100)",
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

        # The pages for an open pull request expect it to have an event, so
        # keep the most recent one regardless of its age
        latest_open = {}
        for pk, pr_id in (
            models.Event.objects.filter(pull_request__closed=False)
            .order_by("created", "pk")
            .values_list("pk", "pull_request")
        ):
            latest_open[pr_id] = pk

        # Job.last_modified is bumped on every save (creation, step updates,
        # completion, invalidation, cancellation), so it is the last activity.
        # Only delete an event once every job on it is old.
        events = (
            models.Event.objects.filter(
                cause=models.Event.PULL_REQUEST, last_modified__lt=cutoff
            )
            .exclude(jobs__last_modified__gte=cutoff)
            .exclude(pk__in=latest_open.values())
        )
        # Closed pull requests left without events, regardless of age. Open ones
        # are skipped because they have no events while being created.
        prs = models.PullRequest.objects.filter(closed=True)

        if dryrun:
            prefix = "DRY RUN: "
            counts = self.dryrun_counts(events, prs)
        else:
            prefix = ""
            counts = self.delete(events, prs, batch_size)

        self.stdout.write(
            "%sDeleted %s pull request events not modified since %s"
            % (prefix, counts[models.Event], cutoff)
        )
        self.stdout.write(
            "%sDeleted %s jobs and %s step results"
            % (prefix, counts[models.Job], counts[models.StepResult])
        )
        self.stdout.write(
            "%sDeleted %s closed pull requests" % (prefix, counts[models.PullRequest])
        )
        self.stdout.write(
            "%sDeleted %s unused commits" % (prefix, counts[models.Commit])
        )

    def dryrun_counts(self, events, prs):
        remaining = models.Event.objects.exclude(pk__in=events.values("pk"))
        commits = (
            models.Commit.objects.filter(
                Q(event_head__in=events.values("pk"))
                | Q(event_base__in=events.values("pk"))
            )
            .exclude(event_head__in=remaining)
            .exclude(event_base__in=remaining)
            .distinct()
        )
        return {
            models.Event: events.count(),
            models.Job: models.Job.objects.filter(
                event__in=events.values("pk")
            ).count(),
            models.StepResult: models.StepResult.objects.filter(
                job__event__in=events.values("pk")
            ).count(),
            models.PullRequest: prs.exclude(events__in=remaining).count(),
            models.Commit: commits.count(),
        }

    def delete(self, events, prs, batch_size):
        """
        Deletes the events and the commits that they leave unused, followed by
        the closed pull requests without events. The matching events are found
        once up front and then deleted batch_size at a time to avoid one huge
        transaction. Deleting cascades to the jobs and their step results, test
        statistics and change logs.
        """
        counts = Counter()
        pks = list(events.order_by("pk").values_list("pk", flat=True))
        for i in range(0, len(pks), batch_size):
            with transaction.atomic():
                # Filter again in case anything changed since the pks were found
                batch = events.filter(pk__in=pks[i : i + batch_size])
                commit_pks = set()
                for head, base in batch.values_list("head", "base"):
                    commit_pks.update((head, base))
                counts.update(self.count_deleted(batch.delete()))
                commits = models.Commit.objects.filter(
                    pk__in=commit_pks,
                    event_head__isnull=True,
                    event_base__isnull=True,
                )
                counts.update(self.count_deleted(commits.delete()))

        prs = prs.filter(events__isnull=True)
        pks = list(prs.order_by("pk").values_list("pk", flat=True))
        for i in range(0, len(pks), batch_size):
            batch = prs.filter(pk__in=pks[i : i + batch_size])
            counts.update(self.count_deleted(batch.delete()))
        return counts

    def count_deleted(self, result):
        """
        Converts the per model label counts returned by QuerySet.delete() to be
        keyed by model.
        """
        return {apps.get_model(label): count for label, count in result[1].items()}
