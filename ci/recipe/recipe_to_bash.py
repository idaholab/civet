#!/usr/bin/env python
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

"""
Converts a recipe given in a .cfg file into a full bash shell script
which would be similar to what CIVET would end up running.
"""
from __future__ import unicode_literals, absolute_import
import argparse, sys, os
import re
from RecipeReader import RecipeReader

def read_script(filename):
    top_dir = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
    script_file = os.path.join(top_dir, filename)
    with open(script_file, "r") as f:
        out = f.read()
        return out

def step_functions(recipe):
    step_cmds = ''
    for step in recipe["steps"]:
        step_cmds += "function step_%s\n{\n" % step["position"]
        for key, value in step["environment"].items():
            step_cmds += write_env(key, value, "  local")
        step_cmds += '  local step_name="%s"\n' % step["name"]
        step_cmds += '  local step_position="%s"\n' % step["position"]
        script = read_script(step["script"])
        for l in script.split('\n'):
            if l.strip():
                step_cmds += '  %s\n' % l
            else:
                step_cmds += "\n"
        step_cmds += "}\nexport -f step_%s\n\n" % step["position"]

    step_cmds += "function step_exit()\n"
    step_cmds += '{\n'
    step_cmds += '  if bash -c $1; then\n'
    step_cmds += '    printf "\\n$1 passed\\n\\n"\n'
    step_cmds += '  elif [ "$2" == "True" ]; then\n'
    step_cmds += '    printf "\\n$1 failed. Aborting\\n\\n"\n'
    step_cmds += '    exit 1\n'
    step_cmds += '  else\n'
    step_cmds += '    printf "\\n$1 failed but continuing\\n\\n"\n'
    step_cmds += '  fi\n'
    step_cmds += '}\n\n'
    # now write out all the functions
    for step in recipe["steps"]:
        step_cmds += "step_exit step_%s %s\n" % (step["position"], step["abort_on_failure"])
    return step_cmds

def write_env(key, value, prefix="export"):
    return '%s %s="%s"\n' % (prefix, key, re.sub("^BUILD_ROOT", "$BUILD_ROOT", value))

def recipe_to_bash(recipe,
        base_repo,
        base_branch,
        base_sha,
        head_repo,
        head_branch,
        head_sha,
        pr,
        push,
        manual,
        build_root,
        moose_jobs,
        args):
    script = "#!/bin/bash\n"
    script += '# Generated by: %s %s\n' % (__file__, ' '.join(args))
    script += '# Script for job %s\n' % recipe["filename"]
    script += '# It is a good idea to redirect stdin, ie "./script.sh  < /dev/null"\n'
    script += '# Be sure to have the proper modules loaded as well.\n'
    script += '\n\n'
    script += 'module list\n'

    script += 'export BUILD_ROOT="%s"\n' % build_root
    script += 'export MOOSE_JOBS="%s"\n' % moose_jobs
    script += '\n\n'

    script += 'export CIVET_RECIPE_NAME="%s"\n' % recipe["name"]
    script += 'export CIVET_BASE_REPO="%s"\n' % base_repo
    script += 'export CIVET_BASE_SSH_URL="%s"\n' % base_repo
    script += 'export CIVET_BASE_REF="%s"\n' % base_branch
    script += 'export CIVET_BASE_SHA="%s"\n' % base_sha
    script += 'export CIVET_HEAD_REPO="%s"\n' % head_repo
    script += 'export CIVET_HEAD_REF="%s"\n' % head_branch
    script += 'export CIVET_HEAD_SHA="%s"\n' % head_sha
    script += 'export CIVET_HEAD_SSH_URL="%s"\n' % head_repo
    script += 'export CIVET_JOB_ID="1"\n'
    cause_str = ""
    if pr:
        cause_str = "Pull Request"
    elif push:
        cause_str = "Push"
    elif manual:
        cause_str = "Manual"
    script += 'export CIVET_EVENT_CAUSE="%s"\n' % cause_str
    script += '\n\n'

    for source in recipe["global_sources"]:
        s = read_script(source)
        script += "# %s\n%s\n" % (source, s)

    script += "\n\n"
    for key, value in recipe["global_env"].items():
        script += write_env(key, value)

    script += "\n\n"
    script += step_functions(recipe)
    return script

def convert_recipe(args):
    parser = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument("--recipe", dest="recipe", help="The recipe file to convert.", required=True)
    parser.add_argument("--output", dest="output", help="Where to write the script to")
    parser.add_argument("--build-root", dest="build_root", default="/tmp/", help="Where to set BUILD_ROOT")
    parser.add_argument("--num-jobs", dest="num_jobs", default="4", help="What to set MOOSE_JOBS to")
    parser.add_argument("--head", nargs=3, dest="head", help="Head repo to work on. Format is: repo branch sha", required=True)
    parser.add_argument("--base", nargs=3, dest="base", help="Base repo to work on. Format is: repo branch sha", required=True)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--pr", action="store_true")
    group.add_argument("--push", action="store_true")
    group.add_argument("--manual", action="store_true")
    parsed = parser.parse_args(args)
    dirname = os.path.dirname(os.path.realpath(__file__))
    parent_dir = os.path.dirname(dirname)
    # RecipeReader takes a relative path from the base repo directory
    real_path = os.path.realpath(parsed.recipe)
    rel_path = os.path.relpath(real_path, parent_dir)
    try:
        reader = RecipeReader(parent_dir, rel_path)
        recipe = reader.read()
    except Exception as e:
        print("Recipe '%s' is not valid: %s" % (real_path, e))
        return 1
    try:
        script = recipe_to_bash(recipe,
            base_repo=parsed.base[0],
            base_branch=parsed.base[1],
            base_sha=parsed.base[2],
            head_repo=parsed.head[0],
            head_branch=parsed.head[1],
            head_sha=parsed.head[2],
            pr=parsed.pr,
            push=parsed.push,
            manual=parsed.manual,
            build_root=parsed.build_root,
            moose_jobs=parsed.num_jobs,
            args=args,
            )
        if parsed.output:
            with open(parsed.output, "w") as f:
                f.write(script)
        else:
            print(script)
    except Exception as e:
        print("Failed to convert recipe: %s" % e)
        return 1

if __name__ == "__main__":
    convert_recipe(sys.argv[1:])
