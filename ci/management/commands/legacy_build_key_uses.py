from __future__ import unicode_literals, absolute_import
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from ci import models
from datetime import timedelta


class Command(BaseCommand):
    help = (
        "List the repositories that had jobs claimed with a legacy (integer) "
        "build key in the given number of days, along with the clients that "
        "claimed them. Once nothing is listed, settings.ALLOW_LEGACY_BUILD_KEYS "
        "can be set to False."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            type=int,
            default=30,
            help="List uses in this many days (default: 30)",
        )

    def handle(self, *args, **options):
        days = options["days"]
        if days < 1:
            raise CommandError("--days must be at least 1")

        cutoff = timezone.now() - timedelta(days=days)
        uses = (
            models.LegacyBuildKeyUse.objects.filter(last_used__gte=cutoff)
            .select_related("user__server", "repository__user")
            .order_by("repository__user__name", "repository__name", "-last_used")
        )

        repo = None
        count = 0
        for use in uses:
            if use.repository != repo:
                repo = use.repository
                count += 1
                self.stdout.write("%s:" % repo)
            self.stdout.write(
                "  user %s, client %s, ip %s: %s uses in total, last %s"
                % (
                    use.user,
                    use.client_name,
                    use.ip,
                    use.uses,
                    use.last_used.strftime("%Y-%m-%d %H:%M:%S %Z"),
                )
            )

        self.stdout.write(
            "%s repositories used legacy build keys in the last %s days" % (count, days)
        )
