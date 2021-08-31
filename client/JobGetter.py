
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
import requests
import traceback
import json
import logging
from requests.packages.urllib3.exceptions import InsecureRequestWarning
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

logger = logging.getLogger("civet_client")

class JobGetter(object):
    def __init__(self, client_info):
        """
        Input:
          client_info: A dictionary containing the following keys
            servers: The URL of the server.
            build_configs: A list of build configs to listen for.
            client_name: The name of the running client
            ssl_verify: Whether to use SSL verification when making a request.
            request_timeout: The timeout when making a request
            build_key: The build_key to be used.
        """
        super(JobGetter, self).__init__()
        self.client_info = client_info
        self._headers = {b"User-Agent": b"INL-CIVET-Client/1.0 (+https://github.com/idaholab/civet)"}

    def find_job(self):
        """
        Tries to find and claim a job to run.
        Return:
          The job information if a job was successfully claimed. Otherwise None
        """
        jobs = self.get_possible_jobs()

        if jobs:
            logger.info('Found {} possible jobs at {}'.format(len(jobs), self.client_info["server"]))
            job = self.claim_job(jobs)
            return job
        return None

    def get_possible_jobs(self):
        """
        Request a list of jobs from the server.
        Returns a dict of the jobs.
        If the server is down, just raise a ServerException and move on.
        This way we don't waste time contacting the bad server when
        we could be running jobs.
        Return:
          None if no jobs or error occurred, else a list of availabe of jobs
        """
        job_url = "{}/client/ready_jobs/{}/{}/".format(self.client_info["server"],
                self.client_info["build_key"],
                self.client_info["client_name"])

        logger.debug('Trying to get jobs at {}'.format(job_url))
        try:
            # Keep this timeout low; if we fail to get a job, continue on to the next server
            # We don't want to hang around waiting if someone else has work
            response = requests.get(job_url,
                    headers=self._headers,
                    verify=self.client_info["ssl_verify"],
                    timeout=5)
            response.raise_for_status()
            data = response.json()
            if 'jobs' not in data:
                err_str = 'While retrieving jobs, server gave invalid JSON : %s' % data
                logger.error(err_str)
                return None
            return data['jobs']
        except Exception as e:
            err_str = "Can't get possible jobs at {}. Check URL.\nError: {}".format(self.client_info["server"], e)
            logger.warning(err_str)
            return None

    def claim_job(self, jobs):
        """
        We have a list of jobs from the server. Now try
        to claim one that matches our config so that
        other clients won't run it.
        Input:
          jobs: A list of jobs as returned by get_possible_jobs()
        Return:
          None if we couldn't claim a job, else the dict of job data that we claimed
        """
        logger.info("Checking %s jobs to claim" % len(jobs))
        for job in jobs:
            config = job['config']
            if config not in self.client_info["build_configs"]:
                logger.info("Incomptable config %s : Known configs : %s" % (config, self.client_info["build_configs"]))
                continue

            claim_json = {
              'job_id': job['id'],
              'config': config,
              'client_name': self.client_info["client_name"],
            }

            try:
                url = "{}/client/claim_job/{}/{}/{}/".format(self.client_info["server"],
                        self.client_info["build_key"],
                        config,
                        self.client_info["client_name"])
                in_json = json.dumps(claim_json, separators=(',', ': '))
                response = requests.post(url,
                        in_json,
                        headers=self._headers,
                        verify=self.client_info["ssl_verify"],
                        timeout=self.client_info["request_timeout"])
                response.raise_for_status()
                claim = response.json()
                if claim.get('success'):
                    logger.info("Claimed job %s config %s on recipe %s" % (job['id'],
                        config,
                        claim['job_info']['recipe_name']))
                    return claim
                else:
                    logger.info("Failed to claim job %s. Response: %s" % (job['id'], claim))
            except Exception:
                logger.warning('Tried and failed to claim job %s. Error: %s' % (job['id'], traceback.format_exc()))

        logger.info('No jobs to run')
        return None
