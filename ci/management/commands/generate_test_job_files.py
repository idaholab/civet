
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

from __future__ import unicode_literals, absolute_import
from django.core.management.base import BaseCommand
from ci.tests import utils
from ci.client import views
from django.test.client import RequestFactory
from django.test import override_settings
from django.urls import reverse
from django.conf import settings
import shutil, os
import json
import traceback

class Command(BaseCommand):
    help = "Generate the claim_response.json file that the client testing uses."

    @override_settings(INSTALLED_GITSERVERS=[utils.github_config()])
    def handle(self, *args, **options):
        factory = RequestFactory()
        client = utils.create_client()
        job = utils.create_job()
        user = job.recipe.build_user

        orig_recipe_dir = settings.RECIPE_BASE_DIR
        recipe_dir = utils.create_recipe_dir()
        settings.RECIPE_BASE_DIR = recipe_dir

        try:
            args=[user.build_key, client.name]
            request = factory.get(reverse("ci:client:ready_jobs", args=args))
            reply = views.ready_jobs(request, user.build_key, client.name)

            args = [user.build_key, job.config.name, client.name]
            claim_job_url = reverse("ci:client:claim_job", args=args)
            data = json.dumps({"job_id": job.pk})
            request = factory.post(claim_job_url, data, content_type="application/json")
            reply = views.claim_job(request, user.build_key, job.config.name, client.name)

            if reply.status_code == 200:
                this_file = os.path.realpath(__file__)
                test_dir = os.path.join(os.path.dirname(this_file), "..", "..", "..", "client", "tests")
                fname = os.path.join(test_dir, "claim_response.json")
                with open(fname, "w") as f:
                    json.dump(json.loads(reply.content), f, indent=2, sort_keys=True)
                    f.write("\n")
            else:
                self.stderr.write(reply.status_code)
                self.stderr.write(reply.content)
        except Exception as e:
            self.stderr.write(traceback.format_exc())
            self.stderr.write("Error occurred: %s" % e)
        job.recipe.delete()
        shutil.rmtree(recipe_dir)
        settings.RECIPE_BASE_DIR = orig_recipe_dir
        settings.RECIPE_BASE_DIR = orig_recipe_dir
