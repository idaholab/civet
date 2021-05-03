from django_daemon_command.management.base import DaemonCommand
import sys
import traceback

class Command(DaemonCommand):
    #sleep = 5

    def process(self,*args,**options):
    	sleep = 5
    	print("a")
    	self.stdout.write("a")