
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
import os
from ci.recipe import file_utils
from django.utils.six import StringIO
try:
    import configparser
except ImportError:
    import ConfigParser as configparser

def add_list(config, recipe, recipe_key, section, prefix):
    l = recipe.get(recipe_key, [])
    if l:
        config.add_section(section)
    for i, dep in enumerate(l):
        config.set(section, "%s%s" % (prefix, i), dep)

def write_recipe_to_string(recipe):
    config = configparser.ConfigParser()
    config.optionxform = str
    config.add_section("Main")
    sections = ["steps",
            "global_sources",
            "global_env",
            "pullrequest_dependencies",
            "manual_dependencies",
            "push_dependencies",
            ]

    for key, value in recipe.items():
        if key not in sections:
            if isinstance(value, list):
                config.set("Main", key, ','.join(value))
            else:
                config.set("Main", key, str(value))

    add_list(config, recipe, "pullrequest_dependencies", "PullRequest Dependencies", "recipe")
    add_list(config, recipe, "push_dependencies", "Push Dependencies", "recipe")
    add_list(config, recipe, "manual_dependencies", "Manual Dependencies", "recipe")
    add_list(config, recipe, "global_sources", "Global Sources", "source")

    global_env = recipe.get("global_env", {})
    if global_env:
        config.add_section("Global Environment")
    for key, value in global_env.items():
        config.set("Global Environment", key, str(value))

    steps = recipe.get("steps", [])
    for step in steps:
        name = step["name"]
        config.add_section(name)
        for key, value in step.items():
            if key != "name" and key != "environment" and key != "position":
                config.set(name, key, str(value))
        for key, value in step["environment"].items():
            config.set(name, key, str(value))
    output = StringIO()
    config.write(output)
    return output.getvalue()

def write_recipe_to_repo(repo_dir, recipe, filename):
    """
    Get an option from the config file and convert it to its proper type based on the default.
    Input:
      repo_dir: str: path to recipe repo dir
      recipe: dict of values as created by RecipeReader
      filename: .cfg file to write
    Return:
      bool: True on success, else False
    """
    full_path = os.path.join(repo_dir, filename)
    if not file_utils.is_subdir(full_path, repo_dir):
        print("Not a valid recipe filename: %s" % filename)
        return False

    data = write_recipe_to_string(recipe)

    with open(full_path, "w") as f:
        f.write(data)

    return True
