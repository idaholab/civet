
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
import models
import logging
logger = logging.getLogger('ci')

class GitCommitData(object):
    """
    Creates or gets the required DB tables for a
    GitCommit
    """

    def __init__(self, owner, repo, ref, sha, ssh_url, server):
        """
        Constructor.
        Input:
          owner: str: Owner of the repository
          repo: str: Name of the repository
          ref: str: Branch on the repository
          sha: str: SHA of the commit
          ssh_url: str: ssh URL to the repo
          server: models.GitServer: The Git server
        """
        self.owner = owner
        self.server = server
        self.repo = repo
        self.ref = ref
        self.sha = sha
        self.ssh_url = ssh_url
        self.user_created = False
        self.user_record = None
        self.repo_created = False
        self.repo_record = None
        self.branch_created = False
        self.branch_record = None
        self.commit_created = False
        self.commit_record = None

    def create_branch(self):
        """
        Creates up to the branch.
        """
        self.user_record, self.user_created = models.GitUser.objects.get_or_create(name=self.owner, server=self.server)
        if self.user_created:
            logger.info("Created %s user %s:%s" % (self.server.name, self.user_record.name, self.user_record.build_key))

        self.repo_record, self.repo_created = models.Repository.objects.get_or_create(user=self.user_record, name=self.repo)
        if self.repo_created:
            logger.info("Created %s repo %s" % (self.server.name, str(self.repo_record)))

        self.branch_record, self.branch_created = (models.Branch.objects
                    .get_or_create(repository=self.repo_record, name=self.ref))
        if self.branch_created:
            logger.info("Created %s branch %s" % (self.server.name, str(self.branch_record)))

    def create(self):
        """
        Will ensure that commit exists in the DB.
        Return:
          The models.Commit that is created.
        """
        self.create_branch()
        self.commit_record, self.commit_created = models.Commit.objects.get_or_create(branch=self.branch_record, sha=self.sha)
        if self.commit_created:
            logger.info("Created %s commit %s" % (self.server.name, str(self.commit_record)))

        if not self.commit_record.ssh_url and self.ssh_url:
            self.commit_record.ssh_url = self.ssh_url
            self.commit_record.save()

        return self.commit_record

    def __str__(self):
        return "%s/%s:%s:%s" % (self.owner, self.repo, self.ref, self.sha[:7])

    def remove(self):
        """
        After a user calls create(), this will delete the records created.
        """
        if self.commit_record and self.commit_created:
            self.commit_record.delete()
            self.commit_record = None
        if self.branch_record and self.branch_created:
            self.branch_record.delete()
            self.branch_record = None
        if self.repo_record and self.repo_created:
            self.repo_record.delete()
            self.repo_record = None
        if self.user_record and self.user_created:
            self.user_record.delete()
            self.user_record = None

    def exists(self):
        q = models.Commit.objects.filter(branch__repository__user__server=self.server,
                branch__repository__user__name=self.owner,
                branch__repository__name=self.repo,
                branch__name=self.ref,
                sha=self.sha)
        return q.exists()
