#!/usr/bin/env python

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

"""
This is currently not used anywhere.
Just some utilities that will help automate
some of the tedious tasks like creating
PRs, commits, etc.
But needs a lot more work.
"""

import requests
import os
import git
import json

# set to te
test_users = []
github_api = 'https://api.github.com'
github = 'https://github.com'
script_dir = os.path.dirname(os.path.abspath(__file__)) + '/../../../../test_repos'
access_token = "<access_token>"
headers = {'Content-type': 'application/json', 'Accept': 'application/json'}

def local_repo_dir(user, repo):
  return '{}/{}/{}'.format(script_dir, user, repo)


def update_repo(user, repo):
  repo_dir = local_repo_dir(user, repo)
  if os.path.exists(repo_dir):
    print('Pull at directory {}'.format(repo_dir))
    git_repo = git.Repo(repo_dir)
    git_repo.remotes.origin.pull()
  else:
    github_repo_name = '{}/{}/{}'.format(github, user, repo)
    print('Cloning from {} to {}'.format(github_repo_name, repo_dir))
    git_repo = git.Repo.clone_from(github_repo_name, repo_dir)

def update_repos(users):
  for user in users:
    repo_url = '{}/users/{}/repos'.format(github_api, user)
    response = requests.get(repo_url)
    data = response.json()
    for repo in data:
      name = repo['name']
      update_repo(user, name)

def get_pull_requests(user, repo):
  pr_url = '{}/repos/{}/{}/pulls'.format(github_api, user, repo)
  response = requests.get(pr_url, headers=headers)
  data = response.json()
  prs = []
  for pr in data:
    head = pr['head']
    base = pr['base']
    head_data = {
          'owner' : head['user']['login'],
          'repo' : head['repo']['name'],
          'branch' : head['ref'],
          }
    base_data = {
          'owner' : base['user']['login'],
          'repo' : base['repo']['name'],
          'branch' : base['ref'],
          }
    pr_data = {
        'head' : head_data,
        'base' : base_data,
        }
    prs.append(pr_data)
  return prs


def get_branch(user, repo, branch):
  update_repo(user, repo)
  repo_dir = local_repo_dir(user, repo)
  gitrepo = git.Repo(repo_dir)
  #from_gitrepo.git.branch('--set-upstream-to=origin/{}'.format(from_branch), from_branch)
  gitbranch = gitrepo.create_head(branch, 'HEAD')
  gitrepo.head.reference = gitbranch
  gitrepo.head.reset(index=True, working_tree=True)
  return gitrepo

def create_pull_request(from_user, from_repo, from_branch, to_user, to_repo, to_branch):
  # first, see if there is already a pull request
  # for this configuration
  open_prs = get_pull_requests(to_user, to_repo)
  for pr in open_prs:
    if (pr['head']['owner'] == from_user and
        pr['head']['repo'] == from_repo and
        pr['head']['branch'] == from_branch and
        pr['base']['branch'] == to_branch):
      print('Already have an open pull request')
      return

  update_repo(from_user, from_repo)
  update_repo(to_user, to_repo)
  from_gitrepo = get_branch(from_user, from_repo, from_branch)
  readme = '{}/{}'.format(from_gitrepo.working_dir, 'README.md')

  with open(readme, 'r+') as f:
    try:
      num = int(f.read())
    except:
      num = 0
    num = num + 1
    f.seek(0)
    f.write(str(num))
    f.truncate()
  from_gitrepo.index.add([os.path.abspath(readme)])
  from_gitrepo.index.commit('Automated commit')
  from_gitrepo.remotes.origin.push(from_branch)
  pr_url = '{}/repos/{}/{}/pulls?access_token={}'.format(github_api, to_user, to_repo, access_token)
  print(pr_url)
  pr_data = {"title": 'Automated pr {}'.format(num),
      'head': '{}:{}'.format(from_user, from_branch),
      'base': to_branch,
      'body': 'Automated request',
      }
  response = requests.post(pr_url, data=json.dumps(pr_data), headers=headers)
  data = response.json()
  with open('auto_pr_open_{}.json'.format(data['number']), 'w') as f:
      f.write(json.dumps(data, indent=4))

def create_push(user, repo, from_branch, to_branch):
  pass

if __name__ == "__main__":
  #update_repos(test_users)
  create_pull_request('testmb02', 'repo03', 'devel', 'testmb', 'repo03', 'devel')
