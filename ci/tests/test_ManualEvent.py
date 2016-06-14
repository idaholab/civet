from ci import models, ManualEvent
import DBTester
import utils

class Tests(DBTester.DBTester):
  def setUp(self):
    super(Tests, self).setUp()
    self.create_default_recipes()

  def create_data(self, branch=None, user=None, latest="1"):
    if branch == None:
      branch = self.branch
    if user == None:
      user = self.build_user
    manual = ManualEvent.ManualEvent(user, branch, latest)
    request = self.factory.get('/')
    request.session = {} # the default RequestFactory doesn't have a session
    return manual, request

  def test_bad_branch(self):
    other_branch = utils.create_branch(name="foo", user=self.build_user)
    manual, request = self.create_data(branch=other_branch)
    # Make sure if there is a manual event and there are no recipes for the branch
    # we don't leave anything around
    # This shouldn't create an event or any jobs.
    self.set_counts()
    manual.save(request)
    self.compare_counts()

  def test_bad_user(self):
    other_build_user = utils.create_user(name="bad_build_user")
    manual, request = self.create_data(user=other_build_user)
    # Make sure we only get recipes for the correct build user
    # This shouldn't create an event or any jobs.
    self.set_counts()
    manual.save(request)
    self.compare_counts()

  def test_valid(self):
    manual, request = self.create_data()
    # a valid Manual, should just create an event and 1 jobs
    self.set_counts()
    manual.save(request)
    self.compare_counts(events=1, jobs=1, ready=1, commits=1, active=1, active_repos=1)

    # saving again shouldn't do anything
    self.set_counts()
    manual.save(request)
    self.compare_counts()

  def test_multiple(self):
    manual, request = self.create_data()
    self.set_counts()
    manual.save(request)
    self.compare_counts(events=1, jobs=1, ready=1, commits=1, active=1, active_repos=1)
    # now try another event on the Manual
    # it should just create more jobs
    old_ev = models.Event.objects.first()
    manual, request = self.create_data(latest="10")
    self.set_counts()
    manual.save(request)
    self.compare_counts(events=1, jobs=1, ready=1, commits=1, active=1)
    old_ev.refresh_from_db()
    self.assertEqual(old_ev.status, models.JobStatus.NOT_STARTED)
    self.assertFalse(old_ev.complete)

  def test_recipe(self):
    manual, request = self.create_data()
    self.set_counts()
    manual.save(request)
    self.compare_counts(events=1, jobs=1, ready=1, commits=1, active=1, active_repos=1)

    # now try another event on the Manual but with a new recipe.
    manual_recipe = models.Recipe.objects.filter(cause=models.Recipe.CAUSE_MANUAL).latest()
    new_recipe = utils.create_recipe(name="New recipe", user=self.build_user, repo=self.repo, branch=self.branch, cause=models.Recipe.CAUSE_MANUAL)
    new_recipe.filename = manual_recipe.filename
    new_recipe.save()
    manual_recipe.current = False
    manual_recipe.save()

    manual, request = self.create_data(latest="10")
    self.set_counts()
    manual.save(request)
    self.compare_counts(events=1, jobs=1, ready=1, commits=1, active=1)
    self.assertEqual(manual_recipe.jobs.count(), 1)
    self.assertEqual(new_recipe.jobs.count(), 1)

    # save the same Manual and make sure the jobs haven't changed
    # and no new events were created.
    self.set_counts()
    manual.save(request)
    self.compare_counts()

  def test_change_recipe(self):
    manual, request = self.create_data()
    self.set_counts()
    manual.save(request)
    self.compare_counts(events=1, jobs=1, ready=1, commits=1, active=1, active_repos=1)
    # This scenario is one where the event already exists but the
    # for some reason the same event gets called and the recipes have changed.
    # Nothing should change
    manual_recipe = models.Recipe.objects.filter(cause=models.Recipe.CAUSE_MANUAL).latest()
    new_recipe = utils.create_recipe(name="New recipe", user=self.build_user, repo=self.repo, branch=self.branch, cause=models.Recipe.CAUSE_MANUAL)
    new_recipe.filename = manual_recipe.filename
    new_recipe.save()
    manual_recipe.current = False
    manual_recipe.save()

    self.set_counts()
    manual.save(request)
    self.compare_counts()
    self.assertEqual(manual_recipe.jobs.count(), 1)
    self.assertEqual(new_recipe.jobs.count(), 0)
