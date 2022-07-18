
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
from django.test import SimpleTestCase
from django.test import override_settings
from ci.tests import utils as test_utils
from client import inl_client
import os, shutil, tempfile, stat
from client import settings, BaseClient
from client.tests import utils

@override_settings(INSTALLED_GITSERVERS=[test_utils.github_config()])
class Tests(SimpleTestCase):
    def setUp(self):
        self.log_dir = tempfile.mkdtemp()
        self.orig_home_env = os.environ["HOME"]
        os.environ['HOME'] = self.log_dir
        base_dir = '{}/civet'.format(self.log_dir)
        os.mkdir(base_dir)
        base_dir += '/logs'
        os.mkdir(base_dir)
        self.orig_servers = settings.SERVERS
        self.orig_manage_build_root = settings.MANAGE_BUILD_ROOT
        self.default_args = ['--client', '0', '--daemon', 'stop', '--configs', 'linux-gnu', '--build-root', '/foo/bar']

    def tearDown(self):
        shutil.rmtree(self.log_dir)
        settings.SERVERS = self.orig_servers
        settings.MANAGE_BUILD_ROOT = self.orig_manage_build_root
        os.environ["HOME"] = self.orig_home_env

    def create_client(self, args):
        c, cmd = inl_client.commandline_client(args)
        BaseClient.setup_logger() # logger on stdout
        claimed_job = utils.read_json_test_file("claimed_job.json")
        c.client_info["single_shot"] = True
        c.client_info["update_step_time"] = 1
        c.client_info["server_update_time"] = 1
        c.client_info["ssl_cert"] = False # not needed but will get another line of coverage
        if claimed_job['config'] not in c.get_client_info('build_configs'):
            c.add_config(claimed_job['config'])
        server = ("https://<server1>", "1234", False)
        settings.SERVERS.append(server)
        c.client_info["servers"] = [ s[0] for s in settings.SERVERS ]

        return {"client": c, "daemon": cmd, "server": server, "claimed_job": claimed_job}

    def test_check_settings(self):
        # Can't create client if SERVERS isn't there
        del settings.SERVERS
        with self.assertRaises(Exception):
            self.create_client(self.default_args)

        # Can't create client if SERVERS isn't a list
        settings.SERVERS = "foo"
        with self.assertRaises(Exception):
            self.create_client(self.default_args)

        # OK
        settings.SERVERS = self.orig_servers
        self.create_client(self.default_args)

        # Set MANAGE_BUILD_ROOT by default
        del settings.MANAGE_BUILD_ROOT
        self.create_client(self.default_args)

        # Can't create client if MANAGE_BUILD_ROOT isn't a bool
        settings.MANAGE_BUILD_ROOT = "foo"
        with self.assertRaises(Exception):
            self.create_client(self.default_args)

        # OK
        settings.MANAGE_BUILD_ROOT = self.orig_manage_build_root
        self.create_client(self.default_args)

    def test_get_build_root(self):
        c = self.create_client(self.default_args)['client']

        self.assertNotIn('BUILD_ROOT', c.get_environment())
        with self.assertRaises(BaseClient.ClientException):
            c.get_build_root()

        c.set_environment('BUILD_ROOT', '/foo/bar')
        self.assertEqual(c.get_build_root(), '/foo/bar')

    def test_build_root_exists(self):
        c = self.create_client(self.default_args)['client']

        temp_dir = tempfile.TemporaryDirectory()
        build_root = temp_dir.name + "/build_root"
        os.mkdir(build_root)
        c.set_environment('BUILD_ROOT', build_root)
        self.assertEqual(c.build_root_exists(), True)
        temp_dir.cleanup()

        c.set_environment('BUILD_ROOT', '/foo/bar')
        self.assertEqual(c.build_root_exists(), False)

    def test_remove_build_root(self):
        c = self.create_client(self.default_args)['client']

        temp_dir = tempfile.TemporaryDirectory()
        build_root = temp_dir.name + "/build_root"
        os.mkdir(build_root)

        # Add some content, and make it all read only
        foodir = os.path.join(build_root, 'foo')
        foofile = os.path.join(foodir, 'foo')
        os.mkdir(foodir)
        with open(foofile, 'w') as f:
            f.write('foo')
        os.chmod(foofile, stat.S_IREAD | stat.S_IRGRP | stat.S_IROTH)
        os.chmod(foodir, stat.S_IREAD | stat.S_IRGRP | stat.S_IROTH)

        c.set_environment('BUILD_ROOT', build_root)
        c.remove_build_root()

        with self.assertRaises(BaseClient.ClientException):
            c.remove_build_root()

        temp_dir.cleanup()

    def test_create_build_root(self):
        c = self.create_client(self.default_args)['client']

        temp_dir = tempfile.TemporaryDirectory()
        build_root = temp_dir.name + "/build_root"
        c.set_environment('BUILD_ROOT', build_root)
        c.create_build_root()
        with self.assertRaises(BaseClient.ClientException):
            c.create_build_root()
        temp_dir.cleanup()

        c.set_environment('BUILD_ROOT', '/foo/bar')
        with self.assertRaises(FileNotFoundError):
            c.create_build_root()
