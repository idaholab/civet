
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
from django.http import HttpResponse, Http404
from django.conf import settings
from django.shortcuts import redirect, get_object_or_404
from django.contrib import messages
from ci import models, Permissions
import os

import logging
logger = logging.getLogger('ci')

def start_session_by_name(request, name):
    """
    When we are testing we often can't sign in successfully because
    it involves a callback from the server which will fail. This will
    simulate the process for a user that is already in the DB and
    has a valid token.
    Should only be active in DEBUG mode.
    Input:
      request: django.http.HttpRequest
      name: str: name to start the session for
    Return:
      django.http.HttpResponse based object
    """
    if not settings.DEBUG:
        raise Http404()

    user = get_object_or_404(models.GitUser, name=name)
    if not user.token:
        raise Http404('User %s does not have a token.' % user.name )
    user.server.auth().set_browser_session_from_user(request.session, user)
    messages.info(request, 'Started debug session for user "%s" on %s' % (user.name, user.server.name))
    return redirect('ci:main')

def start_session(request, user_id):
    """
    When we are testing we often can't sign in successfully because
    it involves a callback from the server which will fail. This will
    simulate the process for a user that is already in the DB and
    has a valid token.
    Should only be active in DEBUG mode.
    Input:
      request: django.http.HttpRequest
      user_id: int: database PK to start the session for
    Return:
      django.http.HttpResponse based object
    """
    if not settings.DEBUG:
        raise Http404()

    user = get_object_or_404(models.GitUser, pk=user_id)
    if not user.token:
        raise Http404('User %s does not have a token.' % user.name )
    user.server.auth().set_browser_session_from_user(request.session, user)
    messages.info(request, 'Started debug session for user "%s" on %s' % (user.name, user.server.name))
    return redirect('ci:main')

def read_recipe_file(filename):
    """
    Utility function to get a script from the recipe directory.
    Used in job_script().
    Input:
      filename: str: Filename relative to the base recipe directory.
    Return:
      str: Contents of file or None if there was a problem
    """
    fname = '{}/{}'.format(settings.RECIPE_BASE_DIR, filename)
    if not os.path.exists(fname):
        return None
    with open(fname, 'r') as f:
        return f.read()

def job_script(request, job_id):
    """
    Creates a single shell script that would be similar to what the client ends up running.
    Used for debugging.
    Input:
      job_id: models.Job.pk
    Return:
      Http404 if the job doesn't exist or the user doesn't have permission, else HttpResponse
    """
    job = get_object_or_404(models.Job, pk=job_id)
    perms = Permissions.job_permissions(request.session, job)
    if not perms['is_owner']:
        logger.warning("Tried to get job script for %s: %s but not the owner" % (job.pk, job))
        raise Http404('Not the owner')
    script = '<pre>#!/bin/bash'
    script += '\n# Script for job {}'.format(job)
    script += '\n# Note that BUILD_ROOT and other environment variables set by the client are not set'
    script += '\n# It is a good idea to redirect stdin, ie "./script.sh  < /dev/null"'
    script += '\n\n'
    script += '\nmodule purge'

    script += '\nexport BUILD_ROOT=""'
    script += '\nexport MOOSE_JOBS="1"'
    script += '\n\n'
    recipe = job.recipe
    for prestep in recipe.prestepsources.all():
        script += '\n{}\n'.format(read_recipe_file(prestep.filename))

    for env in recipe.environment_vars.all():
        script += '\nexport {}="{}"'.format(env.name, env.value)

    script += '\nexport CIVET_RECIPE_NAME="{}"'.format(job.recipe.name)
    script += '\nexport CIVET_JOB_ID="{}"'.format(job.pk)
    script += '\nexport CIVET_RECIPE_ID="{}"'.format(job.recipe.pk)
    script += '\nexport CIVET_COMMENTS_URL="{}"'.format(job.event.comments_url)
    script += '\nexport CIVET_BASE_REPO="{}"'.format(job.event.base.repo())
    script += '\nexport CIVET_BASE_REF="{}"'.format(job.event.base.branch.name)
    script += '\nexport CIVET_BASE_SHA="{}"'.format(job.event.base.sha)
    script += '\nexport CIVET_BASE_SSH_URL="{}"'.format(job.event.base.ssh_url)
    script += '\nexport CIVET_HEAD_REPO="{}"'.format(job.event.head.repo())
    script += '\nexport CIVET_HEAD_REF="{}"'.format(job.event.head.branch.name)
    script += '\nexport CIVET_HEAD_SHA="{}"'.format(job.event.head.sha)
    script += '\nexport CIVET_HEAD_SSH_URL="{}"'.format(job.event.head.ssh_url)
    script += '\nexport CIVET_EVENT_CAUSE="{}"'.format(job.recipe.cause_str())
    script += '\nexport CIVET_BUILD_CONFIG="{}"'.format(job.config.name)
    script += '\n\n'

    count = 0
    step_cmds = ''
    for step in recipe.steps.order_by('position').all():
        script += '\nfunction step_{}\n{{'.format(count)
        script += '\n\tlocal CIVET_STEP_NUM="{}"'.format(step.position)
        script += '\n\tlocal CIVET_STEP_POSITION="{}"'.format(step.position)
        script += '\n\tlocal CIVET_STEP_NAME="{}"'.format(step.name)
        script += '\n\tlocal CIVET_STEP_ABORT_ON_FAILURE="{}"'.format(step.abort_on_failure)
        script += '\n\tlocal CIVET_STEP_ALLOED_TO_FAIL="{}"'.format(step.allowed_to_fail)

        for env in step.step_environment.all():
            script += '\n\tlocal {}="{}"'.format(env.name, env.value)

        for l in read_recipe_file(step.filename).split('\n'):
            script += '\n\t{}'.format(l.replace('exit 0', 'return 0'))
        script += '\n}\n'
        step_cmds += '\nstep_{}'.format(count)
        count += 1

    script += step_cmds
    script += '</pre>'
    return HttpResponse(script)
