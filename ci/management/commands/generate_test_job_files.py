
# Copyright 2016 Battelle Energy Alliance, LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from django.core.management.base import BaseCommand
from ci.tests import utils
from ci.client import views
from django.test.client import RequestFactory
from django.core.urlresolvers import reverse
from django.conf import settings
import shutil, os
import json

class Command(BaseCommand):
    help = "Generate the json files for use with client testing. The resultant *.json files should be moved to client/tests/"

    def handle(self, *args, **options):
        factory = RequestFactory()
        user = utils.get_test_user()
        client = utils.create_client()
        test_job = utils.create_job(user=user)
        test_job.ready = True
        test_job.client = None
        test_job.status = 0
        test_job.save()

        orig_recipe_dir = settings.RECIPE_BASE_DIR
        recipe_dir, repo = utils.create_recipe_dir()
        settings.RECIPE_BASE_DIR = recipe_dir

        # create a prestep to make sure sourcing functions work
        prestep0 = utils.create_prestepsource(filename="prestep0.sh", recipe=test_job.recipe)
        with open(os.path.join(recipe_dir, prestep0.filename), "w") as f:
            f.write('function start_message()\n{\n  echo start "$*"\n}')

        # create a prestep to make sure sourcing functions work
        prestep1 = utils.create_prestepsource(filename="prestep1.sh", recipe=test_job.recipe)
        with open(os.path.join(recipe_dir, prestep1.filename), "w") as f:
            f.write('function end_message()\n{\n  echo "$*"\n}')

        # create a global environment variable to test env works
        # as well as BUILD_ROOT replacement
        utils.create_recipe_environment(name="GLOBAL_NAME", value="BUILD_ROOT/global", recipe=test_job.recipe)
        count = 0
        for s in ["step0", "step1", "step2"]:
            step = utils.create_step(name=s, recipe=test_job.recipe, position=count)
            # create a step environment variable to test env works
            # as well as BUILD_ROOT replacement
            utils.create_step_environment(name="STEP_NAME", value="BUILD_ROOT/%s" % s, step=step)
            step.filename = "%s.sh" % s
            step.save()
            count += 1
            script_filename = os.path.join(recipe_dir, step.filename)
            with open(script_filename, "w") as f:
                print("Writing to %s" % script_filename)
                f.write("echo $GLOBAL_NAME $STEP_NAME\nstart_message {0}\nsleep 1\nend_message {0}\n".format(s))

        # Everything is written to the fake recipe dir, get the request response
        try:
            request = factory.get(reverse("ci:client:ready_jobs", args=[user.build_key, client.name]))
            reply = views.ready_jobs(request, user.build_key, client.name)
            if reply.status_code == 200:
                with open("ready_jobs.json", "wt") as f:
                    json.dump(json.loads(reply.content), f, indent=2, sort_keys=True)

            claim_job_url = reverse("ci:client:claim_job", args=[user.build_key, test_job.config.name, client.name])
            request = factory.post(claim_job_url, json.dumps({"job_id": test_job.pk}), content_type="application/json")
            reply = views.claim_job(request, user.build_key, test_job.config.name, client.name)

            if reply.status_code == 200:
                with open("claimed_job.json", "w") as f:
                    json.dump(json.loads(reply.content), f, indent=2, sort_keys=True)
            else:
                print reply.status_code
                print reply.content
        except Exception as e:
            print("Error occurred: %s" % e)
        test_job.recipe.delete()
        shutil.rmtree(recipe_dir)
        settings.RECIPE_BASE_DIR = orig_recipe_dir
