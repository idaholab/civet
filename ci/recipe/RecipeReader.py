#!/usr/bin/env python

import ConfigParser
import file_utils
import os

class RecipeReader(object):
  """
  Reads a .cfg file and converts into a dict.
  """
  def __init__(self, repo_dir, filename):
    self.repo_dir = repo_dir
    self.filename = filename
    self.hardcoded_sections = ["Main", "Global Sources", "Dependencies", "Global Environment"]
    self.config = ConfigParser.ConfigParser()
    # ConfigParser will default to having case insensitive options and
    # returning lower case versions of options. This is not good
    # for environment variables
    self.config.optionxform = str

    with open(os.path.join(repo_dir, filename), "r") as f:
      self.config.readfp(f)
    self.recipe = {}

  def get_option(self, section, option, default):
    try:
      # set the return value to the same type as default
      if isinstance(default, bool):
        val = self.config.getboolean(section, option)
      elif isinstance(default, list):
        val = self.config.get(section, option)
        val = [l.strip() for l in val.split(',')]
      else:
        val = self.config.get(section, option)

      return val
    except ConfigParser.NoSectionError:
      print("Section '%s' does not exist. Failed to get option '%s'" % (section, option))
      return default
    except ConfigParser.NoOptionError:
      print("Failed to get option '%s' in section '%s'" % (option, section))
      return default
    except ValueError:
      print("Bad value for option '%s' in section '%s'" % (option, section))
      return default

  def check(self):
    ret = True

    if not self.recipe.get("display_name"):
      self.recipe["display_name"] = self.recipe["name"]
      print("'display_name' not set, setting to '%s'" % self.recipe["name"])

    if self.recipe["automatic"].lower() not in ["manual", "automatic", "authorized"]:
      print("Bad value '%s' for automatic. Options are 'manual', 'automatic', or 'authorized'" % self.recipe["automatic"])
      ret = False

    if not self.recipe["trigger_pull_request"] and not self.recipe["trigger_push"] and not self.recipe["trigger_manual"] and not self.recipe["allow_on_pr"]:
      print("self.recipe %s does not have any triggers set" % self.recipe["name"])
      ret = False

    if self.recipe["trigger_push"] and not self.recipe["trigger_push_branch"]:
      print("Push trigger needs a branch")
      ret = False

    if self.recipe["trigger_manual"] and not self.recipe["trigger_manual_branch"]:
      print("Manual trigger needs a branch")
      ret = False

    # FIXME: need to check files exist and are valid
    return ret

  def set_env(self, recipe, key, section):
    env = {}
    for item in self.config.items(section):
      env[item[0]] = item[1]
    recipe[key] = env

  def get_section(self, section_name):
    """
    Get a section name.
    This is used because we want section names
    to be case insensitive.
    """
    for name in self.config.sections():
      if name.lower() == section_name.lower():
        return name
    return ""

  def set_items(self, section_name, recipe_key):
    name = self.get_section(section_name)
    if not name:
      return
    sources = []
    for item in self.config.items(name):
      sources.append(item[1])
    self.recipe[recipe_key] = sources

  def step_sections(self):
    steps = []
    for name in self.config.sections():
      if name not in self.hardcoded_sections:
        steps.append(name)
    return steps

  def set_steps(self):
    steps = []
    for step_section in self.step_sections():
      step_data = {}
      script = self.get_option(step_section, "script", "")
      if not script:
        print("'script' is required in section %s" % step_section)
        return False

      step_data["name"] = step_section
      step_data["script"] = script
      step_data["abort_on_failure"] = self.get_option(step_section, "abort_on_failure", False)
      step_data["allowed_to_fail"] = self.get_option(step_section, "allowed_to_fail", False)
      for item in self.config.items(step_section):
          self.set_env(step_data, "environment", step_section)

      steps.append(step_data)
    self.recipe["steps"] = steps
    return True


  def read(self):
    recipe = {"sha": file_utils.get_file_sha(self.repo_dir, self.filename)}
    recipe["repo_sha"] = file_utils.get_repo_sha(self.repo_dir)
    recipe["filename"] = self.filename
    recipe["name"] = self.get_option("Main", "name", "")
    recipe["display_name"] = self.get_option("Main", "display_name", "")
    recipe["private"] = self.get_option("Main", "private", False)
    recipe["active"] = self.get_option("Main", "active", True)
    recipe["automatic"] = self.get_option("Main", "automatic", "automatic")
    recipe["build_user"] = self.get_option("Main", "build_user", "")
    recipe["build_configs"] = self.get_option("Main", "build_configs", [])
    recipe["trigger_pull_request"] = self.get_option("Main", "trigger_pull_request", False)
    recipe["priority_pull_request"] = self.get_option("Main", "priority_pull_request", 0)
    recipe["trigger_push"] = self.get_option("Main", "trigger_push", False)
    recipe["trigger_push_branch"] = self.get_option("Main", "trigger_push_branch", "")
    recipe["priority_push"] = self.get_option("Main", "priority_push", 0)
    recipe["trigger_manual"] = self.get_option("Main", "trigger_manual", False)
    recipe["trigger_manual_branch"] = self.get_option("Main", "trigger_manual_branch", "")
    recipe["priority_manual"] = self.get_option("Main", "priority_push", 0)
    recipe["allow_on_pr"] = self.get_option("Main", "allow_on_pr", False)
    recipe["repository"] = self.get_option("Main", "repository", "")
    self.recipe = recipe

    if not recipe["name"] or not recipe["build_user"] or not recipe["build_configs"] or not recipe["repository"]:
      print("Missing required options in 'Main' section")
      return {}

    self.set_env(recipe, "global_env", self.get_section("Global Environment"))
    self.set_items("Global Sources", "global_sources")
    self.set_items("Dependencies", "dependencies")
    self.set_steps()

    if not self.check():
      return {}

    return recipe
