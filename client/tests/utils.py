
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
import os, json
from client import BaseClient, INLClient
from ci.tests import utils
from ci import models

def create_json_response(canceled=False, success=True):
    ret = {'status': 'OK'}
    if canceled:
        ret['command'] = 'cancel'
    else:
        ret['command'] = 'none'
    ret['success'] = success
    return ret


def create_step_dict(script_sleep=2, num=1):
    step = {"environment": {"foo": "bar", "step_var_with_root": "BUILD_ROOT/foo"},
        'script': 'echo test_output1; sleep %s; echo test_output2' % script_sleep,
        'stepresult_id': num,
        'step_num': num,
        'step_name': 'step {}'.format(num),
        'step_id': num,
        'abort_on_failure': True,
        'allowed_to_fail': False,
        }
    return step

def create_job_dict(num_steps=1, pk=1):
    job = {'environment': {'base_repo': 'base repo', "var_with_root": "BUILD_ROOT/bar"},
      'recipe_name': 'test_job',
      'prestep_sources': ['prestep'],
      'abort_on_failure': True,
      'job_id': pk,
      'steps':[create_step_dict(num=i) for i in range(num_steps)]
      }
    return job

def default_client_info():
    return {"url": "test_url",
        "client_name": "client_name",
        "server": "https:://<server0>",
        "servers": ["https://<server0>", "https://<server1>"],
        "build_configs": ["linux-gnu"],
        "ssl_verify": False,
        "ssl_cert": "",
        "log_file": "",
        "log_dir": os.path.abspath(os.path.dirname(__file__)),
        "build_key": "1234",
        "single_shot": "False",
        "poll": 30,
        "daemon_cmd": "",
        "request_timeout": 30,
        "update_step_time": 20,
        "server_update_timeout": 5,
        "server_update_interval": 30,
        "max_output_size": 5*1024*1024,
        }

def read_json_test_file(fname):
    dirname = os.path.dirname(os.path.realpath(__file__))
    full_name = os.path.join(dirname, fname)
    with open(full_name, "r") as f:
        json_data = f.read()
        return json.loads(json_data)

def in_call_args(mock_obj, pat, idx):
    for call in mock_obj.call_args_list:
        if str(pat) in str(call[0][idx]):
            return True
    return False

def server_url(stage, client_info, step):
    url_names = {"start_step": "start_step_result",
        "update_step": "update_step_result",
        "complete_step": "complete_step_result",
        }
    url = "%s/client/%s/%s/%s/%s/" % (client_info["server"], url_names[stage], client_info["build_key"], client_info["client_name"], step["stepresult_id"])
    return url

def check_finished(test_obj, claimed_job, client_info, mock_obj):
    finished = "%s/client/job_finished/%s/%s/%s/" % (client_info["server"], client_info["build_key"], client_info["client_name"], claimed_job["job_info"]["job_id"])
    test_obj.assertTrue(in_call_args(mock_obj, finished, 0))

def check_step(test_obj, step, client_info, mock_obj):
    start = "start %s" % step["step_name"]
    done = "done %s" % step["step_name"]
    env_line = "/foo/bar/global /foo/bar/%s" % step["step_name"]
    line = "%s\\n%s\\n%s\\n" % (env_line, start, done)
    test_obj.assertTrue(in_call_args(mock_obj, server_url("start_step", client_info, step), 0))
    test_obj.assertTrue(in_call_args(mock_obj, server_url("update_step", client_info, step), 0))
    test_obj.assertTrue(in_call_args(mock_obj, server_url("complete_step", client_info, step), 0))
    test_obj.assertTrue(in_call_args(mock_obj, step["stepresult_id"], 1))
    test_obj.assertTrue(in_call_args(mock_obj, env_line, 1))
    test_obj.assertTrue(in_call_args(mock_obj, start, 1))
    test_obj.assertTrue(in_call_args(mock_obj, done, 1))
    test_obj.assertTrue(in_call_args(mock_obj, line, 1))

def check_calls(test_obj, claimed_job, client_info, mock_obj):
    for step in claimed_job["job_info"]["steps"]:
        check_step(test_obj, step, client_info, mock_obj)
    check_finished(test_obj, claimed_job, client_info, mock_obj)

def create_base_client(log_dir=None, log_file=None):
    client_info = default_client_info()
    if log_dir != None:
        client_info["log_dir"] = log_dir
    if log_file != None:
        client_info["log_file"] = log_file
    BaseClient.setup_logger() # logger on stdout
    return BaseClient.BaseClient(client_info)

def create_inl_client(log_dir=None, log_file=None):
    client_info = default_client_info()
    BaseClient.setup_logger() # logger on stdout
    return INLClient.INLClient(client_info)

def create_client_job(recipe_dir, name="TestJob", sleep=1, n_steps=3, extra_script=''):
    user = utils.get_test_user()
    recipe = utils.create_recipe(user=user, name=name)
    test_job = utils.create_job(user=user, recipe=recipe)
    test_job.ready = True
    test_job.client = None
    test_job.status = models.JobStatus.NOT_STARTED
    test_job.save()

    # create a prestep to make sure sourcing functions work
    prestep0 = utils.create_prestepsource(filename="prestep0_{}.sh".format(name), recipe=recipe)
    with open(os.path.join(recipe_dir, prestep0.filename), "w") as f:
        f.write('function start_message()\n{\n  echo start "$*"\n}')

    # create a prestep to make sure sourcing functions work
    prestep1 = utils.create_prestepsource(filename="prestep1_{}.sh".format(name), recipe=recipe)
    with open(os.path.join(recipe_dir, prestep1.filename), "w") as f:
        f.write('function end_message()\n{\n  echo end "$*"\n}')

    # create a global environment variable to test env works
    # as well as BUILD_ROOT replacement
    utils.create_recipe_environment(name="GLOBAL_NAME", value="BUILD_ROOT/global", recipe=recipe)
    count = 0
    for s in [f"step{i}".format(i) for i in range(n_steps)]:
        step = utils.create_step(name=s, recipe=recipe, position=count)
        # create a step environment variable to test env works
        # as well as BUILD_ROOT replacement
        utils.create_step_environment(name="STEP_NAME", value="BUILD_ROOT/%s" % s, step=step)
        step.filename = "{}_{}.sh".format(s, name)
        step.save()
        count += 1
        script_filename = os.path.join(recipe_dir, step.filename)
        job_script = "echo $GLOBAL_NAME $recipe_name $STEP_NAME\n"
        job_script += "start_message {0}:{1}\n".format(recipe.name, s)
        job_script += "sleep {0}\n".format(sleep)
        job_script += "end_message {0}:{1}\n".format(recipe.name, s)
        job_script += extra_script
        with open(script_filename, "w") as f:
            f.write(job_script)
    return test_job

def create_job_with_nested_bash(recipe_dir, name="TestJob", sleep=10):
    user = utils.get_test_user()
    recipe = utils.create_recipe(user=user, name=name)
    test_job = utils.create_job(user=user, recipe=recipe)
    test_job.ready = True
    test_job.client = None
    test_job.status = models.JobStatus.NOT_STARTED
    test_job.save()

    step = utils.create_step(name="step0", recipe=recipe, position=0)
    step.filename = "step0.sh"
    step.save()
    script_filename = os.path.join(recipe_dir, step.filename)
    sub_script_filename = os.path.join(recipe_dir, "step0_sub.sh")
    sub_sub_script_filename = os.path.join(recipe_dir, "step0_sub_sub.sh")
    with open(script_filename, "w") as f:
        f.write("#!/bin/bash\necho 'Launching {0}'\n{0}\necho '{0} returned '".format(sub_script_filename))
    with open(sub_script_filename, "w") as f:
        f.write("#!/bin/bash\necho 'Launching {0}'\n{0}\necho '{0} returned'".format(sub_sub_script_filename))

    import stat
    st = os.stat(sub_script_filename)
    os.chmod(sub_script_filename, st.st_mode | stat.S_IEXEC)

    with open(sub_sub_script_filename, "w") as f:
        f.write("#!/bin/bash\necho 'Sleeping {0}...'\nsleep {0}\necho 'Finished sleeping'".format(sleep))
    st = os.stat(sub_sub_script_filename)
    os.chmod(sub_sub_script_filename, st.st_mode | stat.S_IEXEC)
    return test_job

def check_complete_step(self, job, result, extra_step_msg=''):
    global_var = "%s/global" % os.environ["BUILD_ROOT"]
    step_var = "%s/%s" % (os.environ["BUILD_ROOT"], result.name)
    output = "{0} {1} {2}\nstart {1}:{3}\nend {1}:{3}\n{4}".format(global_var, job.recipe.name, step_var, result.name, extra_step_msg)
    self.assertEqual(result.output, output)

def check_complete_job(self, job, n_steps=3, extra_step_msg=''):
    job.refresh_from_db()
    self.assertEqual(job.step_results.count(), n_steps)
    for result in job.step_results.order_by("position"):
        check_complete_step(self, job, result, extra_step_msg)
        self.assertEqual(job.complete, True)
        self.assertEqual(job.status, models.JobStatus.SUCCESS)
        self.assertGreater(job.seconds.total_seconds(), 1)

def check_canceled_job(self, job):
    job.refresh_from_db()
    self.assertEqual(job.step_results.count(), 3)
    found_cancel = False
    for result in job.step_results.order_by("position"):
        if result.status == models.JobStatus.CANCELED:
            self.assertEqual(result.output, "")
            self.assertGreater(job.seconds.total_seconds(), 1)
            found_cancel = True
        elif result.status == models.JobStatus.SUCCESS:
            check_complete_step(self, job, result)
            self.assertGreater(job.seconds.total_seconds(), 1)

    self.assertEqual(found_cancel, True)
    self.assertEqual(job.complete, True)
    self.assertEqual(job.status, models.JobStatus.CANCELED)

def check_stopped_job(self, job):
    job.refresh_from_db()
    self.assertEqual(job.step_results.count(), 0)
    self.assertEqual(job.complete, False)
    self.assertEqual(job.status, models.JobStatus.NOT_STARTED)
