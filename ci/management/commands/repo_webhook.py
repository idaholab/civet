# Copyright 2016-2025 Battelle Energy Alliance, LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from __future__ import unicode_literals, absolute_import
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from ci import models


class Command(BaseCommand):
    help = (
        "Show the webhook URL and secret for a repository, creating them if needed. "
        "The webhook must then be set up on the git server with them."
    )

    def add_arguments(self, parser):
        parser.add_argument("--owner", default=None, help="Owner of the repo")
        parser.add_argument("--repo", default=None, help="The repository name")
        parser.add_argument(
            "--server",
            default=None,
            help="Hostname of the git server. Needed if the repo is on more than one.",
        )
        parser.add_argument(
            "--build-user",
            default=None,
            dest="build_user",
            help="The build user that processes the events. "
            "Needed if more than one build user has recipes on the repo.",
        )
        parser.add_argument(
            "--rotate",
            default=False,
            action="store_true",
            help="Generate a new secret. The webhook on the git server must be updated.",
        )
        parser.add_argument(
            "--delete",
            default=False,
            action="store_true",
            help="Delete the webhook so that it is no longer accepted",
        )
        parser.add_argument(
            "--list",
            default=False,
            action="store_true",
            help="List the URLs of all the webhooks",
        )

    def handle(self, *args, **options):
        if options.get("list"):
            hooks = models.RepositoryWebhook.objects.select_related(
                "repository__user__server", "build_user"
            ).order_by("repository__user__name", "repository__name")
            for hook in hooks:
                self.stdout.write("%s: %s" % (hook, hook.url()))
            return

        repo_rec = self._get_repo(options)
        build_user = self._get_build_user(repo_rec, options.get("build_user"))

        if options.get("delete"):
            deleted, _ = models.RepositoryWebhook.objects.filter(
                repository=repo_rec, build_user=build_user
            ).delete()
            if not deleted:
                raise CommandError("No webhook for %s (%s)" % (repo_rec, build_user))
            self.stdout.write(
                "Deleted the webhook for %s (%s)" % (repo_rec, build_user)
            )
            return

        hook, created = models.RepositoryWebhook.objects.get_or_create(
            repository=repo_rec, build_user=build_user
        )
        if created:
            self.stdout.write("Created a webhook for %s" % hook)
        elif options.get("rotate"):
            hook.secret = models.generate_webhook_secret()
            hook.save()
            self.stdout.write("Generated a new secret for %s" % hook)

        self.stdout.write("URL: %s" % hook.url())
        self.stdout.write("Secret: %s" % hook.secret)
        if repo_rec.server().host_type == settings.GITSERVER_GITHUB:
            self.stdout.write(
                "On GitHub, use content type application/json, enable SSL "
                "verification, and send push, pull request and release events."
            )
        else:
            self.stdout.write(
                "On GitLab, use the secret as the secret token, enable SSL "
                "verification, and send push and merge request events."
            )

    def _get_repo(self, options):
        owner = options.get("owner")
        repo = options.get("repo")
        server = options.get("server")
        if not owner:
            raise CommandError("Need to specify owner")
        if not repo:
            raise CommandError("Need to specify repository")

        repos = models.Repository.objects.filter(user__name=owner, name=repo)
        if server:
            repos = repos.filter(user__server__name=server)
        repos = list(repos.select_related("user__server"))
        if not repos:
            raise CommandError("Invalid repository: %s/%s" % (owner, repo))
        if len(repos) > 1:
            servers = ", ".join(sorted(r.server().name for r in repos))
            raise CommandError(
                "%s/%s is on more than one server (%s), specify --server"
                % (owner, repo, servers)
            )
        return repos[0]

    def _get_build_user(self, repo_rec, name):
        """
        Gets the build user that has recipes on the repository.
        Input:
          repo_rec[models.Repository]: the repository
          name[str]: name of the build user, or None to use the only one
        Return:
          models.GitUser: the build user
        """
        users = models.GitUser.objects.filter(recipes__repository=repo_rec).distinct()
        if name:
            users = users.filter(name=name)
        users = list(users)
        if not users:
            if name:
                raise CommandError("%s has no recipes on %s" % (name, repo_rec))
            raise CommandError("No build user has recipes on %s" % repo_rec)
        if len(users) > 1:
            names = ", ".join(sorted(u.name for u in users))
            raise CommandError(
                "More than one build user has recipes on %s (%s), specify --build-user"
                % (repo_rec, names)
            )
        return users[0]
