from django.core.management.base import BaseCommand
from ci import models
from ci.client import views as client_views

class Command(BaseCommand):
  help = 'Parse step result output to set job OS and modules'

  def handle(self, *args, **options):
    ubuntu_12, created = models.OSVersion.objects.get_or_create(name="Ubuntu", version="12.04", other="precise")
    ubuntu_12_machines = [ "hpcbuild%s_0" % i for i in range(1,6) ]
    ubuntu_12_machines.extend([ "hpcbuild%s_1" % i for i in range(1,6) ])
    ubuntu_12_machines.extend([ "hpcbuild%s_2" % i for i in range(1,6) ])

    ubuntu_14, created = models.OSVersion.objects.get_or_create(name="Ubuntu", version="14.04", other="trusty")
    ubuntu_14_machines = [ "hpcbuild%s_0" % i for i in range(6,11) ]
    ubuntu_14_machines.extend(["hpcbuild%s_1" % i for i in range(6,11) ])

    suse, created = models.OSVersion.objects.get_or_create(name="SUSE LINUX", version="11", other="n/a")
    suse_machines = [ "falcon1_0" ]

    win_machines = ["RAVENHOME"]
    win, created = models.OSVersion.objects.get_or_create(name="Microsoft Windows Server 2012 R2 Standard", version="6.3.9600 N/A Build 9600", other="Member Server")
    for job in models.Job.objects.all():
      job.loaded_modules.clear()
      client_views.set_job_info(job)
      if job.operating_system and job.operating_system.name == "Other":
        if job.client and job.client.name in ubuntu_12_machines:
          job.operating_system = ubuntu_12
          job.save()
        elif job.client and job.client.name in ubuntu_14_machines:
          job.operating_system = ubuntu_14
          job.save()
        elif job.client and job.client.name in win_machines:
          job.operating_system = win
          job.save()
        elif job.client and job.client.name in suse_machines:
          job.operating_system = suse
          job.save()
