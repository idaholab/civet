from os import walk, path, pardir
from operator import itemgetter
import os
import time
from django.core import exceptions
import git

import logging
logger = logging.getLogger('ci')

def to_choices(file_dict):
  """
  file_dict is a dictionary of relative directories as keys
  and a list of files as the value.
  This returns a list of choices suitable for
  a select form field.
  """
  choices = []
  for dname in sorted(file_dict):
    file_choices = [(f, path.basename(f)) for f in sorted(file_dict[dname])]
    choices.append((dname, file_choices))
  return choices

def get_file_dict(base_dir, subdir):
  """
  Given a base directory, get all the files
  in the subdirectory.
  Returns a dictionary of relative subdirectories
  as keys and a list of files as values.
  """
  base_dir = path.realpath(base_dir)
  full_subdir = path.join(base_dir, subdir)
  dir_dict = {}
  for root, subFolders, files in walk(full_subdir):
    dfiles = []
    for f in files:
      full_path = path.realpath(path.join(root, f))
      rel_file = path.relpath(full_path, base_dir)
      dfiles.append(rel_file)
    if dfiles:
      rel_dir = path.relpath(root, base_dir)
      dfiles.sort(key=itemgetter(1))
      dir_dict[rel_dir] = dfiles
  return dir_dict

def get_all_choices(base_dir, user):
  """
  for a username, get a list of filenames that
  the user has access to, all relative to base_dir.
  The return is a dictionary with keys of directory
  names that contain a list of files.
  """
  choices = [(None, 'New file'),]
  user_files = get_file_dict(base_dir, user)
  choices.extend(to_choices(user_files))
  common_files = get_file_dict(base_dir, 'common')
  choices.extend(to_choices(common_files))
  return choices

def is_subdir(suspect_child, suspect_parent):
  suspect_child = path.realpath(suspect_child)
  suspect_parent = path.realpath(suspect_parent)
  relative = path.relpath(suspect_child, start=suspect_parent)
  return not relative.startswith(pardir)

def is_shared_file(base_dir, full_path):
  common_path = path.join(base_dir, 'common', '')
  return is_subdir(full_path, common_path)

def get_filename_in_db(base_dir, username, value):
  """
  Normally the file value will be the relative path from
  the base dir. However, if the user is creating a new file they
  might not put in the directory structure. So detect this and
  put the file in the user directory.
  If there is an invald value then return None, otherwise
  return the value that will be stored in the DB.
  """
  value = path.normpath(value)
  # do realpath on everything so we don't have
  # relative paths like ".." in there
  base_dir = path.realpath(base_dir)
  user_path = path.join(base_dir, username, '') # get the trailing /
  full_path = path.realpath(path.join(base_dir, value))
  # for the file to be valid, it has to be
  # in the 'common' directory or in the username
  # directory
  if not is_shared_file(base_dir, full_path) and not is_subdir(full_path, user_path):
    # the user tried to input a bad path
    # try to put the value after the username
    full_path = path.realpath(path.join(base_dir, username, value))
    if not is_subdir(full_path, user_path):
      return None

  # trim off the base_dir with path seperator
  return full_path[len(base_dir)+1:]

def get_contents(base_dir, filename):
  full_path = path.join(base_dir, filename)
  if not is_subdir(full_path, base_dir):
    # don't allow breaking away from base_dir
    return None

  logger.debug('Getting contents for {}'.format(full_path))
  if path.exists(full_path):
    with open(full_path, 'r') as f:
      data = f.read()
    return data
  return None

def get_versions(base_dir, filename):
  """
  For the givin filename, return a list of tuples
  in the form (sha, commit_time)
  """
  base_dir = path.realpath(base_dir)
  full_path = path.realpath(path.join(base_dir, filename))
  repo = git.Repo(base_dir)
  try:
    shas = repo.git.log('--pretty=%H', '--', full_path).split('\n')
    commits = [repo.rev_parse(c) for c in shas]
    times = [(c.hexsha, time.ctime(c.committed_date)) for c in commits]
    return times
  except Exception as e:
    logger.debug('Problem getting versions for file {}. Error: {}'.format(full_path, e))
    return []

def get_version(base_dir, filename, version):
  versions = get_versions(base_dir, filename)
  shas = [ v[0] for v in versions]

  if version not in shas:
    return None

  repo = git.Repo(base_dir)
  contents = repo.git.show('{}:{}'.format(version, filename))
  return contents

def is_valid_file(base_dir, user, filename):
  base_dir = path.realpath(base_dir)
  user_dir = path.normpath(path.join(base_dir, user))
  common_dir = path.realpath(path.join(base_dir, 'common', ''))
  full_path = path.realpath(path.join(base_dir,  filename, ''))
  return is_subdir(full_path, user_dir) or is_subdir(full_path, common_dir)

def check_save(base_dir, user, filename):
  full_path = path.realpath(path.join(base_dir, filename))
  if not is_valid_file(base_dir, user, filename):
    raise exceptions.SuspiciousOperation('Bad filename')

  if is_shared_file(base_dir, full_path):
    raise exceptions.PermissionDenied('Not allowed to save common files')

  dname = path.dirname(full_path)
  try:
    os.makedirs(dname)
  except OSError as e:
    if not path.isdir(dname):
      raise exceptions.PermissionDenied('Could not create directory: {}'.format(e))

def commit_file(base_dir, user, filename, new_contents, new_file):
  lockfile = path.join(base_dir, '.lockfile')
  lock = git.BlockingLockFile(lockfile)
  try:
    lock._obtain_lock() # will get released on destruction
  except IOError as e:
    # something weird is happening
    raise exceptions.ImproperlyConfigured(str(e))

  full_path = path.realpath(path.join(base_dir, filename))
  try:
    with open(full_path, 'w') as f:
      logger.debug('Writing file {}'.format(full_path))
      f.write(new_contents)
  except Exception as e:
    raise exceptions.PermissionDenied('Could not write file.\nError: {}'.format(e))

  try:
    repo = git.Repo(base_dir)
    repo.index.add([full_path])
    if new_file:
      repo.index.commit('{} created file "{}"'.format(user, filename))
    else:
      repo.index.commit('{} changed file "{}"'.format(user, filename))
  except Exception as e:
    raise exceptions.ImproperlyConfigured('Problem with git.\nError: {}'.format(e))

def save_file(base_dir, user, filename, contents):
  base_dir = path.realpath(base_dir)
  contents = contents.replace('\r', '')
  full_path = path.realpath(path.join(base_dir, filename))
  logger.debug('Trying to save file {}'.format(full_path))

  old_contents = get_contents(base_dir, filename)
  new_file = False
  if old_contents == None:
    new_file = True

  if old_contents != contents:
    check_save(base_dir, user, filename)
    commit_file(base_dir, user, filename, contents, new_file)

