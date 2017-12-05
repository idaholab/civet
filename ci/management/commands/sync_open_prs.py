from django.core.management.base import BaseCommand
from ci import models

class Command(BaseCommand):
    help = 'Close CIVET open PRs that the server says are closed'
    def add_arguments(self, parser):
        parser.add_argument('--dryrun', default=False, action='store_true', help="Don't make any changes, just report what would have happened")
        parser.add_argument('--repo', help="Limit sync to this repository")

    def _get_repos(self, repo):
        if not repo:
            repo_q = models.Repository.objects.filter(active=True).exclude(recipes=None)
        else:
            r = repo.split("/")
            if len(r) != 2:
                raise Exception("Bad repo format. Should be <owner>/<repo_name>")
            repo_q = models.Repository.objects.filter(user__name=r[0], name=r[1], active=True)
        return repo_q

    def handle(self, *args, **options):
        dryrun = options["dryrun"]
        repo_q = self._get_repos(options["repo"])
        self._sync_open_prs(repo_q, dryrun)

    def _sync_open_prs(self, q, dryrun):
        open_on_server_no_civet = []
        for repo in q.all():
            build_user = repo.recipes.last().build_user
            open_prs = repo.get_open_prs_from_server(build_user)
            if open_prs is None:
                self.stdout.write("Error getting open PRs for %s. Skipping." % repo)
                continue

            pr_q = models.PullRequest.objects.filter(closed=False, repository=repo)
            server_pr_ids = [pr["number"] for pr in open_prs]
            civet_pr_ids = []
            # Find PRs that CIVET has open but the doesn't have
            # Close them in CIVET if this isn't a dryrun
            for civet_pr in pr_q.all():
                civet_pr_ids.append(civet_pr.number)
                if civet_pr.number not in server_pr_ids:
                    if not dryrun:
                        self.stdout.write("Closing on CIVET: %s #%s: %s" % (repo, civet_pr.number, civet_pr.title))
                        civet_pr.closed = True
                        civet_pr.save()
                    else:
                        self.stdout.write("DRYRUN: Would close on CIVET: %s #%s: %s" % (repo, civet_pr.number, civet_pr.title))
            # Keep a list of PRs that the Git Server has open but CIVET does not
            for pr in open_prs:
                if pr["number"] not in civet_pr_ids:
                    pr["repo"] = repo
                    open_on_server_no_civet.append(pr)

        if open_on_server_no_civet:
            self.stdout.write("\n%s\nPRs open on server but not open on CIVET:" % ("-"*50))
            for pr in open_on_server_no_civet:
                self.stdout.write("\t%s #%s: %s\t%s" % (pr["repo"], pr["number"], pr["title"], pr["html_url"]))
