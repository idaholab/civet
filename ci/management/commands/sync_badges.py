from __future__ import unicode_literals, absolute_import
from django.core.management.base import BaseCommand
from ci import models

class Command(BaseCommand):
    help = "Sync badges"
    def add_arguments(self, parser):
        parser.add_argument('--dryrun', default=False, action='store_true',
                help="Don't make any changes, just report what would have happened")

    def get_repo(self, server, name):
        try:
            user_name, repo_name = name.split("/")
            user = models.GitUser.objects.get(name=user_name, server=server)
            repo = models.Repository.objects.get(name=repo_name, user=user)
            return repo
        except:
            return None

    def update_repo_badges(self, repo, badges, prefix, dryrun):
        causes = [models.Event.PUSH, models.Event.MANUAL]
        matched = []
        for b in badges:
            try:
                latest_job = models.Job.objects.filter(recipe__filename=b["recipe"],
                        event__cause__in=causes,
                        recipe__repository=repo).latest()
                self.stdout.write("%s%s:%s: Updating badge: %s: %s" % (prefix,
                    repo.server(),
                    repo,
                    b["name"],
                    latest_job.status_str()))
                matched.append(b["recipe"])
                if not dryrun:
                    latest_job.update_badge()
            except models.Job.DoesNotExist:
                # no problem, the job needs to be run then the badge will be updated
                pass
        return matched

    def handle(self, *args, **options):
        dryrun = options["dryrun"]
        prefix = ""
        if dryrun:
            prefix = "DRYRUN:"

        all_matched = {}
        for server in models.GitServer.objects.all():
            repo_settings = server.server_config().get("repository_settings", {})
            if not repo_settings:
                continue
            for name, settings in repo_settings.items():
                badges = settings.get("badges", [])
                if not badges:
                    continue

                repo = self.get_repo(server, name)
                matched = self.update_repo_badges(repo, badges, prefix, dryrun)
                if matched:
                    all_matched[repo] = matched

        for b in models.RepositoryBadge.objects.all():
            existing = all_matched.get(b.repository, [])
            if b.filename not in existing:
                self.stdout.write("%s%s:%s: Removing badge: %s" % (prefix, b.repository.server(), b.repository, b.name))
                if not dryrun:
                    b.delete()
