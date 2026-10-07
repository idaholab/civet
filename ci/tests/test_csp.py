# Copyright 2016-2025 Battelle Energy Alliance, LLC
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
from django.urls import reverse
from django.utils.csp import CSP
from ci.tests import DBTester
import os
import re

TEMPLATE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "templates", "ci"
)
# A script tag without a src attribute is inline script
INLINE_SCRIPT_RE = re.compile(r"<script(?![^>]*\ssrc=)[^>]*>", re.IGNORECASE)
INLINE_HANDLER_RE = re.compile(r"\son[a-z]+\s*=", re.IGNORECASE)
STYLE_RE = re.compile(r"\sstyle\s*=|<style", re.IGNORECASE)


class Tests(DBTester.DBTester):
    def test_header(self):
        response = self.client.get(reverse("ci:main"))
        self.assertEqual(response.status_code, 200)
        policy = response.headers[CSP.HEADER_REPORT_ONLY]
        self.assertIn("default-src 'none'", policy)
        self.assertIn("script-src 'self'", policy)
        self.assertNotIn("unsafe-inline", policy)

    def test_templates_have_no_inline_code(self):
        """
        The policy blocks inline scripts, event handlers and styles, so
        they must not be used in templates.
        """
        for name in sorted(os.listdir(TEMPLATE_DIR)):
            with open(os.path.join(TEMPLATE_DIR, name), "r") as f:
                data = f.read()
            for regex in [INLINE_SCRIPT_RE, INLINE_HANDLER_RE, STYLE_RE]:
                with self.subTest(template=name, check=regex.pattern):
                    self.assertEqual(regex.findall(data), [])
