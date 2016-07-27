
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

import git
import os
import logging
logger = logging.getLogger('ci')

def get_repo_sha(base_dir):
  """
  Get the current sha for a repo.
  Input:
    base_dir: str: path to where the repo resides
  Return:
    str: current SHA of repo, or "" if not a valid repo
  """
  try:
    repo = git.Repo(base_dir)
    return repo.head.object.hexsha
  except Exception:
    logger.warning("Failed to get repo sha for '%s'" % base_dir)
    return ""

def get_contents(base_dir, filename):
  """
  Gets the contents of a file
  Input:
    base_dir: str: path of base directory.
    filename: str: filename relative to base_dir
  Return:
    if valid, str of contents of file, otherwise None
  """
  full_path = os.path.join(base_dir, filename)

  if os.path.exists(full_path):
    with open(full_path, 'r') as f:
      data = f.read()
    return data
  return None
