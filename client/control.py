#!/usr/bin/env python
"""
Controls instances of inl_client.py
This replaces the bash script that started and stopped the clients but didn't do a good job
of restarting clients.
This launches settings.NUM_CLIENTS instances of the INLClient and keeps them as subprocesses.
The primarly purpose and main improvement over the bash script is that this allows for easier
restarting with a fresh copy of the client python code.
"""
import sys, argparse, os
from daemon import Daemon
import settings
import subprocess
import time
import socket
import signal
import select

class ClientsController(object):
  """
  Main class to control the clients.
  It opens a file socket for communication. The various start/stop etc commands
  are sent via there.
  """
  FILE_SOCKET = "/tmp/civet_client_controller.sock"

  def __init__(self):
    self.socket = None
    self.shutdown = False
    self.processes = {}
    self.jobs = {}
    self.timeout = 2
    if os.path.exists(self.FILE_SOCKET):
      raise Exception("%s exists! Is another controller running? If not then remove the file and relaunch" % self.FILE_SOCKET)

    client_dir = os.path.dirname(os.path.realpath(__file__))
    inl_client = os.path.join(client_dir, "inl_client.py")
    for i in range(settings.NUM_CLIENTS):
      self.jobs[i] = [inl_client, "--daemon", "none", "--client", str(i)]

  def remove_socket(self):
    """
    Removes the socket without error
    """
    try:
      os.unlink(self.FILE_SOCKET)
    except OSError:
      pass

  def create_socket(self):
    """
    Clears the old socket and creates a new one.
    """
    self.remove_socket()
    self.socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    self.socket.bind(self.FILE_SOCKET)
    self.socket.listen(1) # We only need 1 queued connection

  def read_cmd(self):
    """
    Try to read a command from the socket and process it.
    """
    read, write, err = select.select([self.socket], [], [], self.timeout)
    if self.socket not in read:
      return
    conn, addr = self.socket.accept()
    data = conn.recv(1024)
    if not data:
      return
    if data == "shutdown":
      self.shutdown = True
      conn.send("Shutting down")
    elif data == "stop":
      msg = self.stop_procs()
      conn.send(msg)
    elif data == "start":
      msg = self.start_all_procs()
      conn.send(msg)
    elif data == "restart":
      msg = self.stop_procs()
      msg += self.start_all_procs()
      conn.send(msg)
    elif data == "graceful":
      msg = self.send_signal(signal.SIGUSR2)
      conn.send(msg)
    elif data == "graceful_restart":
      msg = self.send_signal(signal.SIGUSR2)
      for proc in self.processes.values():
        proc["need_restart"] = True
      conn.send(msg)
    elif data == "status":
      msg = ""
      for p in self.processes.values():
        runtime = p.get("runtime", 0)
        alive = "Dead"
        if p["process"].poll() == None:
          runtime = time.time() - p["start"]
          alive = "Running"
        m, s = divmod(runtime, 60)
        h, m = divmod(m, 60)
        d, h = divmod(h, 24)
        msg += "%s: %s: %d:%02d:%02d:%02d\n" % (p["process"].pid, alive, d, h, m, s)
      conn.send(msg)
    else:
      conn.send("Unknown command: %s" % data)
    conn.close()

  @staticmethod
  def send_cmd(cmd):
    """
    Utility method to send a command to the socket.
    Input:
      cmd: str: Command that will be processed.
    """
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.connect(ClientsController.FILE_SOCKET)
    s.sendall(cmd)
    data = s.recv(1024)
    s.close()
    print(data)

  def send_signal(self, sig):
    """
    Send a signal to all processes that are alive.
    Input:
      sig: int: signal number
    Return:
      str: information on what happened
    """
    ret = ""
    for proc in self.processes.values():
      if proc["process"].poll() == None:
        os.kill(proc["process"].pid, sig)
        ret += "Sent %s to process %s\n" % (sig, proc["process"].pid)
    return ret

  def stop_procs(self):
    """
    Stop all the processes.
    Return:
      str: information on what happened
    """
    ret = ""
    for proc in self.processes.values():
      msg = self.kill_proc(proc)
      if msg:
        ret += msg + "\n"
    return ret

  def kill_proc(self, proc):
    """
    Stop the process if it is alive.
    Input:
      proc: dict: as created in start_proc()
    Return:
      str: information on what happened
    """
    if proc["process"].poll() == None:
      pgid = os.getpgid(proc["process"].pid)
      os.killpg(pgid, signal.SIGTERM)
      proc["process"].terminate()
      proc["runtime"] = time.time() - proc["start"]
      proc["running"] = False
      return "Process %s killed" % proc["process"].pid
    return ""

  def start_all_procs(self):
    """
    Starts all the processes
    Return:
      str: information on what happened
    """
    msg = ""
    for i in self.jobs.keys():
      msg += self.start_proc(i) + "\n"
    return msg

  def start_proc(self, idx):
    """
    Starts process at index idx
    Input:
      idx: int: Index into the jobs dict
    Return:
      str: information on what happened
    """
    j = self.jobs[idx]
    proc = self.processes.get(idx)
    if proc and proc["process"].poll() == None:
      return "Process %s already running" % idx
    p = subprocess.Popen(
        j,
        shell=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        preexec_fn=os.setsid,
        )
    self.processes[idx] = {"process": p, "start": time.time(), "running": True}
    return "Started process %s" % p.pid

  def check_restart(self):
    """
    Check to see if we need to restart any processes
    """
    for idx, proc in self.processes.items():
      if proc.get("need_restart", False) and proc["process"].poll() is not None:
        print("Starting new process on index %s" % idx)
        self.start_proc(idx)
        proc["need_restart"] = False

  def check_dead(self):
    """
    Check to see if any processes are dead.
    """
    for idx, proc in self.processes.items():
      if proc["running"] and proc["process"].poll() is not None:
        proc["runtime"] = time.time() - proc["start"]
        proc["running"] = False

  def run(self):
    """
    Main loop
    """
    self.create_socket()
    for i in self.jobs.keys():
      self.start_proc(i)

    while not self.shutdown:
      self.read_cmd()
      self.check_restart()
      self.check_dead()
    self.stop_procs()
    self.socket.close()
    self.remove_socket()
    return 0

class ControlDaemon(Daemon):
  PID_FILE = "/tmp/civet_client_controller.pid"

  def __init__(self, *args, **kwargs):
    super(ControlDaemon, self).__init__(self.PID_FILE, *args, **kwargs)
    self.controller = ClientsController()

  def run(self):
    self.controller.run()

def main(args):
  parser = argparse.ArgumentParser()
  parser.add_argument('--launch', dest='launch', action="store_true", help="Launches the controller, by default in daemon mode unless --no-daemon is specified")
  parser.add_argument('--no-daemon', dest='no_daemon', action="store_true", help="Don't go into daemon mode")
  parser.add_argument('--shutdown', dest='shutdown', action="store_true", help="Shutdown all clients and the controller")
  parser.add_argument('--start', dest='start', action="store_true", help="Starts up any clients that have been stopped")
  parser.add_argument('--stop', dest='stop', action="store_true", help="Stops all clients. Clients do not finish currently running jobs")
  parser.add_argument('--graceful', dest='graceful', action="store_true", help="Gracefully stops all clients. Clients finish their jobs before stopping")
  parser.add_argument('--graceful-restart', dest='graceful_restart', action="store_true", help="Gracefully stops all clients then restarts them")
  parser.add_argument('--restart', dest='restart', action="store_true", help="Stops all clients then restarts them. Same as doing a --stop then a --start")
  parser.add_argument('--status', dest='status', action="store_true", help="Prints out the current status of the clients")
  if not args:
    parser.print_help()
    return 1
  parsed = parser.parse_args(args)
  if parsed.launch:
    if parsed.no_daemon:
      control = ClientsController()
      return control.run()
    else:
      control = ControlDaemon()
      control.start()
      return 0

  if parsed.shutdown:
    ClientsController.send_cmd("shutdown")
  elif parsed.start:
    ClientsController.send_cmd("start")
  elif parsed.stop:
    ClientsController.send_cmd("stop")
  elif parsed.graceful:
    ClientsController.send_cmd("graceful")
  elif parsed.graceful_restart:
    ClientsController.send_cmd("graceful_restart")
  elif parsed.restart:
    ClientsController.send_cmd("restart")

  if parsed.status:
    ClientsController.send_cmd("status")

if __name__ == "__main__":
  exit(main(sys.argv[1:]))
