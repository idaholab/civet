
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

import requests
from . import utils
from django.test import override_settings
from ci.tests import utils as test_utils
from client import JobGetter
from mock import patch
from ci.tests import DBTester
from client import BaseClient
BaseClient.setup_logger()

@override_settings(INSTALLED_GITSERVERS=[test_utils.github_config()])
class Tests(DBTester.DBTester):
    def create_getter(self):
        self.client_info = utils.default_client_info()
        getter = JobGetter.JobGetter(self.client_info)
        return getter

    @patch.object(requests, 'get')
    def test_get_possible_jobs(self, mock_get):
        g = self.create_getter()

        # test the non error operation
        job_response = {"jobs": "jobs"}
        mock_get.return_value = test_utils.Response(job_response)
        self.set_counts()
        jobs = g.get_possible_jobs()
        self.assertEqual(jobs, job_response["jobs"])
        self.compare_counts()

        # check when the server responds incorrectly
        job_response = {"none": "none"}
        mock_get.return_value = test_utils.Response(job_response)
        self.set_counts()
        jobs = g.get_possible_jobs()
        self.compare_counts()
        self.assertEqual(jobs, None)

        # check when requests has bad status code
        mock_get.return_value = test_utils.Response(job_response, do_raise=True)
        self.set_counts()
        jobs = g.get_possible_jobs()
        self.compare_counts()
        self.assertEqual(jobs, None)

    @patch.object(requests, 'post')
    def test_claim_job(self, mock_post):
        g = self.create_getter()
        j0 = {"config": "unknown_config", "id": 1}
        j1 = {"config": g.client_info["build_configs"][0], "id": 2}
        jobs = [j0, j1]
        response_data = utils.create_json_response()
        response_data['job_info'] = {'recipe_name': 'test'}
        mock_post.return_value = test_utils.Response(response_data)
        # successfull operation
        self.set_counts()
        ret = g.claim_job(jobs)
        self.compare_counts()
        self.assertEqual(response_data, ret)

        # didn't succeed
        response_data["success"] = False
        mock_post.return_value = test_utils.Response(response_data)
        self.set_counts()
        ret = g.claim_job(jobs)
        self.compare_counts()
        self.assertEqual(ret, None)

        # no jobs with matching config
        jobs = [j1]
        self.set_counts()
        ret = g.claim_job(jobs)
        self.compare_counts()
        self.assertEqual(ret, None)

        # try when server problems
        mock_post.return_value = test_utils.Response(response_data, do_raise=True)
        self.set_counts()
        ret = g.claim_job(jobs)
        self.compare_counts()
        self.assertEqual(ret, None)

    @patch.object(requests, 'get')
    @patch.object(requests, 'post')
    def test_find_job(self, mock_post, mock_get):
        g = self.create_getter()

        j0 = {"config": "unknown_config", "id": 1}
        j1 = {"config": g.client_info["build_configs"][0], "id": 2}
        jobs = [j0, j1]
        mock_get.return_value = test_utils.Response({"jobs": jobs})
        response_data = utils.create_json_response()
        response_data['job_info'] = {'recipe_name': 'test'}
        mock_post.return_value = test_utils.Response(response_data)

        # normal operation
        self.set_counts()
        result = g.find_job()
        self.compare_counts()
        self.assertEqual(result, response_data)

        # no jobs
        mock_get.return_value = test_utils.Response([])
        self.set_counts()
        result = g.find_job()
        self.compare_counts()
        self.assertEqual(result, None)
