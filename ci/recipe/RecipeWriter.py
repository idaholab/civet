import ConfigParser
import os
import file_utils
import StringIO

def add_list(config, recipe, recipe_key, section, prefix):
  l = recipe.get(recipe_key, [])
  if l:
    config.add_section(section)
  for i, dep in enumerate(l):
    config.set(section, "%s%s" % (prefix, i), dep)

def WriteRecipeToString(recipe):
  config = ConfigParser.ConfigParser()
  config.optionxform = str
  config.add_section("Main")
  for key, value in recipe.iteritems():
    if key not in ["steps", "global_sources", "global_env", "pullrequest_dependencies", "manual_dependencies", "push_dependencies"]:
      if isinstance(value, list):
        config.set("Main", key, ' '.join(value))
      else:
        config.set("Main", key, value)

  add_list(config, recipe, "pullrequest_dependencies", "PullRequest Dependencies", "recipe")
  add_list(config, recipe, "push_dependencies", "Push Dependencies", "recipe")
  add_list(config, recipe, "manual_dependencies", "Manual Dependencies", "recipe")
  add_list(config, recipe, "global_sources", "Global Sources", "source")

  global_env = recipe.get("global_env", {})
  if global_env:
    config.add_section("Global Environment")
  for key, value in global_env.iteritems():
    config.set("Global Environment", key, value)

  steps = recipe.get("steps", [])
  for step in steps:
    name = step["name"]
    config.add_section(name)
    for key, value in step.iteritems():
      if name != "name":
        config.set(name, key, value)

  output = StringIO.StringIO()
  config.write(output)
  return output.getvalue()

def WriteRecipe(repo_dir, recipe, filename):
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

  data = WriteRecipeToString(recipe)

  with open(full_path, "w") as f:
    f.write(data)

  return True
