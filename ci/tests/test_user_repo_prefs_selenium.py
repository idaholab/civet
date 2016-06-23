import SeleniumTester
import utils
from django.core.urlresolvers import reverse
from django.test import override_settings

class Tests(SeleniumTester.SeleniumTester):
  def create_repos(self):
    repos = []
    for i in range(3):
      repo = utils.create_repo(name="repo%s" % i)
      repo.active = True
      repo.save()
      repos.append(repo)
    return repos

  @SeleniumTester.test_drivers()
  def test_no_login(self):
    self.create_repos()
    url = reverse('ci:user_repo_settings')
    self.get(url)
    with self.assertRaises(Exception):
      self.selenium.find_element_by_id("repo_settings")

  @SeleniumTester.test_drivers()
  @override_settings(DEBUG=True)
  def test_valid(self):
    repos = self.create_repos()
    user = repos[0].user
    start_session_url = reverse('ci:start_session', args=[user.pk])
    self.get(start_session_url)
    self.wait_for_js()

    self.assertEqual(user.preferred_repos.count(), 0)
    url = reverse('ci:user_repo_settings')
    self.get(url)
    form = self.selenium.find_element_by_id("repo_settings")
    form.submit()
    self.wait_for_js()
    self.assertEqual(user.preferred_repos.count(), 0)

    for i in range(3):
      form = self.selenium.find_element_by_id("repo_settings")
      elem = self.selenium.find_element_by_xpath("//input[@value='%s']" % repos[i].pk)
      elem.click()
      form.submit()
      self.wait_for_js()
      self.assertEqual(user.preferred_repos.count(), i+1)
      pref_repos = [ repo for repo in user.preferred_repos.all() ]
      for j in range(i+1):
        self.assertEqual(pref_repos[j], repos[j])
