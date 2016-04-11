from django.test import SimpleTestCase
from client import BaseClient
from . import utils

class Tests(SimpleTestCase):
  def test_log_dir(self):
    c = utils.create_base_client()
    self.assertIn(c.client_info["client_name"], c.client_info["log_file"])
    # dir exists but can't write
    with self.assertRaises(BaseClient.ClientException):
      c.set_log_dir("/var")

    # dir does not exist
    with self.assertRaises(BaseClient.ClientException):
      c.set_log_dir("/var/aafafafaf")

    # not set, should just return
    c.set_log_dir("")

    # test it out from __init__
    with self.assertRaises(BaseClient.ClientException):
      c = utils.create_base_client(log_dir="/afafafafa/")

    # test it out from __init__
    with self.assertRaises(BaseClient.ClientException):
      c = utils.create_base_client(log_dir="", log_file="")

  def test_log_file(self):
    c = utils.create_base_client(log_file="test_log")
    self.assertIn('test_log', c.client_info["log_file"])

    # can't write
    with self.assertRaises(BaseClient.ClientException):
      c.set_log_file("/var/foo")

    # can't write
    with self.assertRaises(BaseClient.ClientException):
      c.set_log_file("/aafafafaf/fo")

    # not set, should just return
    c.set_log_file("")
