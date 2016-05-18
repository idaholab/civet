import ConfigParser
import file_utils
import os
import utils

class RecipeReader(object):
  """
  Reads a .cfg file and converts into a dict.
  The syntax of a file follows the ConfigParser syntax.
  Class variables:
    ALLOWED_CONFIGS: The allowed build configs used in recipes
  """
  ALLOWED_CONFIGS = [ "linux-gnu",
      "linux-clang",
      "linux-intel",
      "linux-trilinos",
      "linux-gnu-coverage",
      "linux-gnu-timing",
      "linux-valgrind",
      "linux-hpc",
      "linux-package-build",
      "linux-package-build-test",
      "win-mingw",
      "osx-clang",
      "test_build",
      "linux-gui",
      "linux-gnu64",
      ]
  def __init__(self, repo_dir, filename):
    """
    Constructor.
    Input:
      repo_dir: str: Path to the recipe repo
      filename: .cfg file to read
    """
    self.repo_dir = repo_dir
    self.filename = filename
    self.hardcoded_sections = ["Main", "Global Sources", "PullRequest Dependencies", "Push Dependencies", "Manual Dependencies", "Global Environment"]
    self.config = ConfigParser.RawConfigParser()
    # ConfigParser will default to having case insensitive options and
    # returning lower case versions of options. This is not good
    # for environment variables
    self.config.optionxform = str

    with open(os.path.join(repo_dir, filename), "r") as f:
      self.config.readfp(f)
    self.recipe = {}

  def error(self, msg):
    print("%s/%s: %s" % (self.repo_dir, self.filename, msg))

  def get_option(self, section, option, default):
    """
    Get an option from the config file and convert it to its proper type based on the default.
    Input:
      section: section of the config file
      option: key value underneath the section.
      default: Default value if the option or section isn't found
    Return:
      value (with same type as default) of the option
    """
    try:
      # set the return value to the same type as default
      if isinstance(default, bool):
        val = self.config.getboolean(section, option)
      elif isinstance(default, list):
        val = self.config.get(section, option)
        val = [l.strip() for l in val.split(',')]
      elif isinstance(default, int):
        val = self.config.getint(section, option)
      else:
        val = self.config.get(section, option)

      return val
    except ConfigParser.NoSectionError:
      self.error("Section '%s' does not exist. Failed to get option '%s'" % (section, option))
      return default
    except ConfigParser.NoOptionError:
      #self.error("Failed to get option '%s' in section '%s'" % (option, section))
      return default
    except ValueError:
      self.error("Bad value for option '%s' in section '%s'" % (option, section))
      return default

  def check(self):
    """
    Make sure the recipe is valid.
    Checks the existence of filenames in the repo but not whether they are valid.
    Return:
      bool: True if valid, otherwise False
    """
    ret = True

    if not self.recipe.get("display_name"):
      self.recipe["display_name"] = self.recipe["name"]
      self.error("'display_name' not set, setting to '%s'" % self.recipe["name"])

    if self.recipe["automatic"].lower() not in ["manual", "automatic", "authorized"]:
      self.error("Bad value '%s' for automatic. Options are 'manual', 'automatic', or 'authorized'" % self.recipe["automatic"])
      ret = False

    if not self.recipe["trigger_pull_request"] and not self.recipe["trigger_push"] and not self.recipe["trigger_manual"] and not self.recipe["allow_on_pr"]:
      self.error("self.recipe %s does not have any triggers set" % self.recipe["name"])
      ret = False

    if self.recipe["trigger_push"] and not self.recipe["trigger_push_branch"]:
      self.error("Push trigger needs a branch")
      ret = False

    if self.recipe["trigger_manual"] and not self.recipe["trigger_manual_branch"]:
      self.error("Manual trigger needs a branch")
      ret = False

    if len(self.recipe["sha"]) != 40 or len(self.recipe["repo_sha"]) != 40:
      self.error("Recipes need to be in a repo!")
      ret = False

    if len(self.recipe["build_configs"]) == 0:
      self.error("You need to specify a build config!")
      ret = False

    for config in self.recipe["build_configs"]:
      if config not in self.ALLOWED_CONFIGS:
        self.error("Build config '%s' not an allowed configuration" % config)
        ret = False

    repo = utils.parse_repo(self.recipe["repository"])
    if not repo:
      self.error("Invalid repository!")
      ret = False

    if not self.check_files_valid("global_sources", "global source"):
      ret = False
    if not self.check_files_valid("pullrequest_dependencies", "pullrequest dependency"):
      ret = False
    if not self.check_files_valid("push_dependencies", "push dependency"):
      ret = False
    if not self.check_files_valid("manual_dependencies", "manual dependency"):
      ret = False

    if self.filename in self.recipe["pullrequest_dependencies"] or self.filename in self.recipe["push_dependencies"] or self.filename in self.recipe["manual_dependencies"]:
      self.error("Can't have a a dependency on itself!")
      ret = False

    if len(self.recipe["steps"]) == 0:
      self.error("No steps specified!")
      ret = False

    for step in self.recipe["steps"]:
      if not file_utils.is_valid_file(self.repo_dir, step["script"]):
        self.error("Not a valid step file: %s" % step["script"])
        ret = False

    return ret

  def check_files_valid(self, key, desc):
    """
    Check to see if a list of filenames are valid.
    Input:
      key: str: key into the recipes dict to get the list of files
      desc: str: Description used in the error message.
    Return:
      bool: True if all are valid, else False
    """
    ret = True
    for fname in self.recipe[key]:
      if not file_utils.is_valid_file(self.repo_dir, fname):
        self.error("Not a valid %s file in %s: %s" % (desc, self.recipe["name"], fname))
        ret = False
    return ret

  def set_env(self, recipe, key, section):
    """
    Used to set the "environment" section.
    Currently all key=value pairs are stored in the environment
    Input:
      recipe: dict: current recipe
      key: key in the recipe dict to insert into
      section: section to get key=value pairs from
    """
    env = {}
    for item in self.config.items(section):
      env[item[0]] = item[1]
    recipe[key] = env

  def get_section(self, section_name):
    """
    Get a section name.
    This is used because we want section names to be case insensitive.
    Input:
      section_name: str: Section name to get
    Return:
      str: Name of the section as it is in the .cfg file or "" if not found.
    """
    for name in self.config.sections():
      if name.lower() == section_name.lower():
        return name
    return ""

  def set_items(self, section_name, recipe_key):
    """
    Puts all the values of a section into the recipe dict as a list, ignoring the option name.
    Input:
      section_name: Section to get options from.
      recipe_key: key of the recipe dict to put the values
    """
    name = self.get_section(section_name)
    if not name:
      self.recipe[recipe_key] = []
      return
    sources = []
    for item in self.config.items(name):
      sources.append(item[1])
    self.recipe[recipe_key] = sources

  def step_sections(self):
    """
    Get sections of steps.
    Step sections are any sections not in one of the hardcoded sections.
    They are inserted in the same order as they are in the file.
    Return:
      list[str]: Section names
    """
    steps = []
    lowered_sections = [ i.lower() for i in self.hardcoded_sections ]
    for name in self.config.sections():
      if name.lower() not in lowered_sections:
        steps.append(name)
    return steps

  def set_steps(self):
    """
    Sets the information for a step.
    Return:
      bool: True if all the required information was specified, else False
    """
    steps = []
    for step_section in self.step_sections():
      step_data = {}
      script = self.get_option(step_section, "script", "")
      if not script:
        self.error("'script' is required in section %s" % step_section)
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


  def read(self, do_check=True):
    """
    Read in the recipe and return a dict of the contents.
    Return:
      dict of values read in from the .cfg file or an empty dict if there was a problem.
    """
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
    recipe["priority_manual"] = self.get_option("Main", "priority_manual", 0)
    recipe["allow_on_pr"] = self.get_option("Main", "allow_on_pr", False)
    recipe["repository"] = self.get_option("Main", "repository", "")
    self.recipe = recipe

    if not recipe["name"] or not recipe["build_user"] or not recipe["build_configs"] or not recipe["repository"]:
      self.error("Missing required options in 'Main' section")
      return {}

    global_env_section = self.get_section("Global Environment")
    if global_env_section:
      self.set_env(recipe, "global_env", global_env_section)
    self.set_items("Global Sources", "global_sources")
    self.set_items("Pullrequest Dependencies", "pullrequest_dependencies")
    self.set_items("Push Dependencies", "push_dependencies")
    self.set_items("Manual Dependencies", "manual_dependencies")
    if not self.set_steps():
      self.error("Invalid steps!")
      return {}

    if do_check and not self.check():
      self.error("Failed to pass check!")
      return {}

    return recipe
