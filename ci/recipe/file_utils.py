
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

import os
import subprocess

def is_subdir(suspect_child, suspect_parent):
    """
    Check to see if a path is a subdir of another path.
    Input:
      suspect_child: The full path of what you think is the sub path.
      suspect_parent: The full path to the parent directory to test against.
    Return:
      bool: True if suspect_child is a subdir of suspect_parent
    """
    suspect_child = os.path.realpath(suspect_child)
    suspect_parent = os.path.realpath(suspect_parent)
    relative = os.path.relpath(suspect_child, start=suspect_parent)
    return not relative.startswith(os.pardir)

def get_contents(base_dir, filename):
    """
    Gets the contents of a file, with some checking.
    This checks to make sure filename has base_dir as a parent directory.
    This is to prevent things like filename="../../secret_file"
    Input:
      base_dir: str: path of base directory.
      filename: str: filename relative to base_dir
    Return:
      if valid, str of contents of file, otherwise None
    """
    full_path = os.path.join(base_dir, filename)
    if not is_subdir(full_path, base_dir):
        # don't allow breaking away from base_dir
        return None

    if os.path.exists(full_path):
        with open(full_path, 'r') as f:
            data = f.read()
        return data
    return None

def is_valid_file(base_dir, filename):
    """
    Check if a file is a valid file within a parent directory.
    This checks to make sure filename doesn't try to break out of
    the parent directory
    Input:
      base_dir: str: path to parent directory
      filename: str: filename relative to base_dir
    Return:
      bool: True if filename exists and lives in the parent directory
    """
    base_dir = os.path.realpath(base_dir)
    full_path = os.path.realpath(os.path.join(base_dir,  filename, ''))
    return is_subdir(full_path, base_dir) and os.path.exists(full_path)

def get_repo_sha(base_dir):
    """
    Get the current sha for a repo.
    Input:
      base_dir: str: path to where the repo resides
    Return:
      str: current SHA of repo, or "" if not a valid repo
    """
    try:
        sha = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=base_dir)
        return sha.strip()
    except Exception as e:
        print(("Failed to get repo sha for '%s': %s" % (base_dir, e)))
        return ""

def get_file_sha(repo_dir, filename):
    """
    Get the SHA for a filename in a repo.
    Input:
      repo_dir: str: The full directory to the repository
      filename: str: Filename relative to repo_dir
    Return:
      str: current SHA of filename, or "" if not a valid repo
    """
    try:
        sha = subprocess.check_output(['git', 'ls-files', filename], cwd=repo_dir).strip()
        if not sha:
            return ""
        sha = subprocess.check_output(['git', 'hash-object', filename], cwd=repo_dir)
        return sha.strip()
    except Exception as e:
        print(("Failed to get sha for '%s/%s': %s" % (repo_dir, filename, e)))
        return ""
