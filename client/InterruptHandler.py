import signal

class InterruptHandler(object):
  def __init__(self, message_q, sig=[]):
    self.sig = sig
    self.message_q = message_q
    self.message = None
    self.triggered = False

    self.orig_handler = {}
    for sig in self.sig:
      self.orig_handler[sig] = signal.getsignal(sig)

    def handler(signum, sigframe):
      if self.message:
        self.message_q.put(self.message)
      self.triggered = True

    for sig in self.sig:
      signal.signal(sig, handler)

  def set_message(self, msg):
    self.message = msg

# This can be used if you need to use this with "with"
#  def __exit__(self, type, value, tb):
#    for sig in self.sig:
#      signal.signal(sig, self.original_handler[sig])
