from ci import models, GitCommitData
import DBTester
import utils

class Tests(DBTester.DBTester):
  def test_create(self):
    commit = utils.create_commit()
    gitcommit = GitCommitData.GitCommitData(
        commit.user().name,
        commit.repo().name,
        commit.branch.name,
        commit.sha,
        'some ssh url',
        commit.server(),
        )
    # everything exists so no change
    self.set_counts()
    commit2 = gitcommit.create()
    self.compare_counts()
    self.assertEqual(commit, commit2)

    # new commit
    gitcommit = GitCommitData.GitCommitData(
        'no_exist',
        'no_exist',
        'no_exist',
        '1234',
        'ssh_url',
        models.GitServer.objects.first(),
        )
    self.set_counts()
    commit = gitcommit.create()
    self.compare_counts(users=1, repos=1, branches=1, commits=1)

    # same commit should return same
    self.set_counts()
    new_commit = gitcommit.create()
    self.compare_counts()
    self.assertEqual(new_commit, commit)

    # set the ssh_url
    commit.ssh_url = ''
    commit.save()
    self.set_counts()
    commit = gitcommit.create()
    self.compare_counts()
    self.assertEqual(commit.ssh_url, 'ssh_url')

  def test_remove(self):
    commit = utils.create_commit()
    gitcommit = GitCommitData.GitCommitData(
        commit.user().name,
        commit.repo().name,
        commit.branch.name,
        commit.sha,
        'some ssh url',
        commit.server(),
        )
    # everything exists so no change
    self.set_counts()
    commit2 = gitcommit.create()
    self.compare_counts()
    self.assertEqual(commit, commit2)

    # nothing was created so now we don't remove anything
    self.set_counts()
    gitcommit.remove()
    self.compare_counts()

    # new commit
    gitcommit = GitCommitData.GitCommitData(
        'no_exist',
        'no_exist',
        'no_exist',
        '1234',
        'ssh_url',
        models.GitServer.objects.first(),
        )
    self.set_counts()
    commit = gitcommit.create()
    self.compare_counts(users=1, repos=1, branches=1, commits=1)
    # everything was created so now we them all
    self.set_counts()
    gitcommit.remove()
    self.compare_counts(users=-1, repos=-1, branches=-1, commits=-1)
