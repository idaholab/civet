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
            help='Specifies how many seconds in the past to start the search. Defaults to 1 day'),
        make_option('--steps', default=False, action='store_true', dest='steps',
            help='Output info on each step that has tests'),
        make_option('--csv', default=False, action='store_true', dest='csv',
          help='Write output in comma separated format: <start date>,<end date>,<num_test_steps>,<num_passed>,<num_skipped>,<num_failed>\nWith the verbose option also set then a comma separated list of steps with their stats are output as well: <date>,<recipe.pk>,<recipe_name>,<step_name>,<passed>,<skipped>,<failed>'),
        )

    def handle(self, *args, **options):
        seconds = options.get('seconds', None)
        show_steps = options.get('steps', False)
        csv = options.get('csv', False)
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
          step_passed = 0
          step_failed = 0
          step_skipped = 0
          output = "\n".join(s.clean_output().split("<br/>"))
          matches = re.findall('>(?P<passed>\d+) passed<.*, .*>(?P<skipped>\d+) skipped<.*, .*>(?P<pending>\d+) pending<.*, .*>(?P<failed>\d+) failed', output, flags=re.IGNORECASE)
          for match in matches:
            step_passed += int(match[0])
            step_failed += int(match[3])
            step_skipped += int(match[1])
          if matches:
            if show_steps:
              if csv:
                print("{},{},{},{},{},{},{}".format(s.last_modified, s.job.recipe.pk, s.job.recipe, s.name, step_passed, step_skipped, step_failed))
              else:
                print("Matched: {}: {}: {}: {}: {}".format(s.pk, s.name, step_passed, step_skipped, step_failed))
            num_steps += 1
          passed += step_passed
          failed += step_failed
          skipped += step_skipped

        if csv:
          now = timezone.localtime(timezone.make_aware(datetime.datetime.utcnow()))
          print("{},{},{},{},{},{}".format(dt, now, num_steps, passed, skipped, failed))
        else:
          print("Since {}".format(dt))
          print("Total test steps: {}".format(num_steps))
          print("Totals: {} passed, {} skipped, {} failed".format(passed, skipped, failed))
