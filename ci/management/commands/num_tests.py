from django.core.management.base import BaseCommand
from django.utils import timezone
from ci import models
from ci.ajax import views
import datetime, re
from optparse import make_option

class Command(BaseCommand):
    help = 'Show the number of tests run in the last 24 hours'
    option_list = BaseCommand.option_list + (
        make_option('--seconds-ago', default=None, dest='seconds', type='int',
            help='Specifies how many seconds in the past to start the search'),
        make_option('--verbose', default=False, action='store_true', dest='verbose',
            help='Be a bit more verbose'),
        )

    def handle(self, *args, **options):
        seconds = options.get('seconds', None)
        verbose = options.get('verbose', False)
        if not seconds:
          seconds = 60*60*24
        this_request = views.get_local_timestamp() - seconds
        dt = timezone.localtime(timezone.make_aware(datetime.datetime.utcfromtimestamp(this_request)))
        steps = models.StepResult.objects.filter(last_modified__gte=dt).order_by('pk')
        passed = 0
        failed = 0
        skipped = 0
        num_steps = 0
        for s in steps:
          m = re.search('(?P<passed>\d+) passed.*, .*>(?P<skipped>\d+) skipped.*, .*>(?P<pending>\d+) pending.*, .*>(?P<failed>\d+) failed', s.clean_output(), flags=re.IGNORECASE)
          if m:
            if verbose:
              print("Matched: {}: {}: {}: {}".format(s.pk, s.name, m.group("passed"), m.group("failed")))
            passed += int(m.group("passed"))
            failed += int(m.group("failed"))
            skipped += int(m.group("skipped"))
            num_steps += 1
        print("Since {}".format(dt))
        print("Total test steps: {}".format(num_steps))
        print("Totals: {} passed, {} skipped, {} failed".format(passed, skipped, failed))
