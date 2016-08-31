
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

import os, subprocess

class Modules(object):
  """
  Used to load the required modules for a job by the client.
  The stock "modulecmd" is a little screwy in that it doesn't always
  return an error code. For example, loading an invalid module will give
  an error message but still return 0.
  """
  def __init__(self):
    """
    Constructor.
    Raises:
      Exception: If we don't have a good modules environmnet.
    """
    super(Modules, self).__init__()
    if not os.environ.has_key("MODULESHOME"):
      raise Exception("No module environment detected")

  def is_exe(self, path):
    return os.path.isfile(path) and os.access(path, os.X_OK)

  def command(self, command, args=[]):
    """
    Executes a module command.
    The output of the system "modulecmd" will output on stdout the commands needed to be performed.
    So we need to "exec" this. Information is on stderr.
    Input:
      command: str: The command to run
      args: A list of arguments to the command
    Return:
      dict:
        success: Whether the command exited normally.
        stdout: Output on stdout
        stderr: Output on stderr
    """
    module_cmd = "%s/bin/modulecmd" % os.environ["MODULESHOME"]
    if not self.is_exe(module_cmd):
      # On the cluster we use the lmod command
      module_cmd = "%s/libexec/lmod" % os.environ["MODULESHOME"]
      if not self.is_exe(module_cmd):
        raise Exception("Command to load modules not found")

    proc = subprocess.Popen([module_cmd, 'python', command] + args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    (output, error) = proc.communicate()
    if proc.returncode == 0:
      exec output
    return {"success": proc.returncode == 0, "stdout": output, "stderr": error}

  def clear_and_load(self, new_mods):
    """
    Clears the modules and load some new ones.
    "module load" seems to always exit 0, even if there is an invalid module.
    Normally there won't be anything on stderr but there will be for an invalid module.
    Input:
      new_mods: A list of new modules to load.
    Raises:
      Exception: If a module failed to load
    """
    self.command("purge")
    ret = self.command("load", new_mods)
    if not ret["success"] or ret["stderr"] != "":
      raise Exception("Tried loading invalid modules: %s" % new_mods)
