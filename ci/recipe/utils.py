import re
def parse_repo(repo):
  """
  Given a repo string, break it up into components.
  Input:
    repo: str: The full repo specification, ie git@github.com:idaholab/civet.git
  Return:
    hostname, owner, repository
  """
  r = re.match("git@(.+):(.+)/(.+)\.git", repo)
  if r:
    return r.group(1), r.group(2), r.group(3)

  r = re.match("git@(.+):(.+)/(.+)", repo)
  if r:
    return r.group(1), r.group(2), r.group(3)

  r = re.match("https://(.+)/(.+)/(.+).git", repo)
  if r:
    return r.group(1), r.group(2), r.group(3)

  r = re.match("https://(.+)/(.+)/(.+)", repo)
  if r:
    return r.group(1), r.group(2), r.group(3)

  print("Failed to parse repo: %s" % repo)

def same_repo(repo0, repo1):
  """
  Determine if two repo strings are the same.
  Input:
    repo0: str: first repo
    repo1: str: second repo
  Return:
    bool: True if they are the same, otherwise False
  """
  info0 = parse_repo(repo0)
  info1 = parse_repo(repo1)
  if not info0 or not info1:
    print("Not same repo: %s: %s" % (repo0, repo1))
    return False
  return info0[0] == info1[0] and info0[1] == info1[1] and info0[2] == info1[2]
