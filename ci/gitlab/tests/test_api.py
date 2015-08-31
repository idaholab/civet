from django.test import TestCase, Client

class APITestCase(TestCase):
  fixtures = ['base.json',]

  def setUp(self):
    self.client = Client()

  def test_install_webhooks(self):
    pass
