
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
            build_keys: A list of build keys
            build_configs: A list of build configs to listen for.
            client_name: The name of the running client
            ssl_verify: Whether to use SSL verification when making a request.
            request_timeout: The timeout when making a request
            build_key: The build_key to be used.
        """
        super(JobGetter, self).__init__()
        self.client_info = client_info
        self._headers = {b"User-Agent": b"INL-CIVET-Client/1.0 (+https://github.com/idaholab/civet)"}
        self._url = f'{self.client_info["server"]}/client/get_job/'

    def check_response(self, response_json):
        expected_values = {'job_id': [int, type(None)],
                           'config': [str, type(None)],
                           'success': [bool, type(None)],
                           'message': [str, type(None)],
                           'status': [str],
                           'job_info': [dict, type(None)],
                           'build_key': [int, type(None)]}
        for key, value_types in expected_values.items():
            if key not in response_json:
                logger.warning(f'Missing key \'{key}\' in {self._url}')
                return False
            response_value = response_json.get(key)
            if type(response_value) not in value_types:
                logger.warning(f'Key \'{key}\' has unexpected type {type(response_value).__name__} from {self._url}')
                return False
        for key in response_json:
            if key not in expected_values:
                logger.warning(f'Unexpected key {key} from {self._url}')
                return False

        return True

    def get_job(self):
        post_data = { 'client_name': self.client_info["client_name"],
                      'build_keys': self.client_info["build_keys"],
                      'build_configs': self.client_info["build_configs"] }
        post_json = json.dumps(post_data, separators=(",", ": "))

        try:
            response = requests.post(self._url,
                                    post_json,
                                    headers=self._headers,
                                    verify=self.client_info["ssl_verify"],
                                    timeout=5)
            response.raise_for_status()
            response_json = response.json()
        except:
            logger.warning('Failed to get job', exc_info=True)
            return None

        # Make sure the values are all as we expect
        if not self.check_response(response_json):
            return None

        # Job isn't available
        if response_json.get('job_id') is None:
            return None

        return response_json
