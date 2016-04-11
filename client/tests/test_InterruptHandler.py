from django.test import SimpleTestCase
from client import InterruptHandler
import signal, os, subprocess
from Queue import Queue

class InterruptHandlerTests(SimpleTestCase):
  def test_handler(self):
    q = Queue()
    i = InterruptHandler.InterruptHandler(q, sig=[signal.SIGUSR1])
    i.set_message("hi")
    self.assertEqual(i.triggered, False)

    script = "sleep 1 && kill -USR1 %s" % os.getpid()
    proc = subprocess.Popen(script, shell=True, executable="/bin/bash", stdout=subprocess.PIPE)
    proc.wait()
    self.assertEqual(i.triggered, True)
    self.assertEqual(q.qsize(), 1)
    msg = q.get(block=False)
    self.assertEqual(msg, "hi")
