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
import ipaddress
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from ci import models


class Command(BaseCommand):
    help = (
        "Register a build client and show the key that it authenticates with. "
        "The key is only shown when it is created, so it must be saved to the "
        "client's key file then."
    )

    def add_arguments(self, parser):
        parser.add_argument("--name", default=None, help="Name of the client")
        parser.add_argument(
            "--build-user",
            default=[],
            action="append",
            dest="build_users",
            help="A user whose jobs the client can run, as <server>:<user>. "
            "Can be given more than once.",
        )
        parser.add_argument(
            "--new",
            default=False,
            action="store_true",
            help="Register a new client even if old clients have the name",
        )
        ip_group = parser.add_mutually_exclusive_group()
        ip_group.add_argument(
            "--ip",
            default=None,
            help="The address that the client must connect from. "
            "If not set, it is the address of the client's first request.",
        )
        ip_group.add_argument(
            "--clear-ip",
            default=False,
            action="store_true",
            dest="clear_ip",
            help="Clear the address, so that the next request from the client sets it",
        )
        action_group = parser.add_mutually_exclusive_group()
        action_group.add_argument(
            "--update",
            default=False,
            action="store_true",
            help="Replace the build users of the client",
        )
        action_group.add_argument(
            "--rotate",
            default=False,
            action="store_true",
            help="Generate a new key. The client's key file must be updated.",
        )
        action_group.add_argument(
            "--delete",
            default=False,
            action="store_true",
            help="Unregister the client so that its key is no longer accepted",
        )
        action_group.add_argument(
            "--list",
            default=False,
            action="store_true",
            help="List the registered clients",
        )

    def handle(self, *args, **options):
        if options.get("list"):
            self._list()
            return

        name = options.get("name")
        if not name:
            raise CommandError("Need to specify --name")
        ip = self._get_ip(options)
        build_users = [self._get_build_user(u) for u in options.get("build_users")]

        update = options.get("update")
        rotate = options.get("rotate")
        clear_ip = options.get("clear_ip")

        with transaction.atomic():
            if options.get("delete"):
                client = self._get_registered(name)
                client.build_key_hash = None
                client.save()
                client.build_users.clear()
                self.stdout.write("Unregistered %s" % name)
                return

            creating = not update and not rotate and bool(build_users)
            if creating:
                client = self._create(name, options.get("new"))
            elif update or rotate or ip or clear_ip:
                client = self._get_registered(name)
            else:
                raise CommandError(
                    "Need to specify --build-user to register %s, or an action" % name
                )

            if update and not build_users:
                raise CommandError("Need to specify --build-user")
            if build_users and not creating and not update:
                raise CommandError(
                    "%s is already registered; use --update to change its build users"
                    % name
                )

            key = None
            if creating or rotate:
                key = client.set_build_key()
            if ip:
                client.ip = ip
            elif clear_ip:
                client.ip = None
            client.save()
            if build_users:
                client.build_users.set(build_users)

        if creating:
            self.stdout.write("Registered %s" % name)
        if update:
            self.stdout.write("Updated the build users of %s" % name)
        if rotate:
            self.stdout.write("Generated a new key for %s" % name)
        if ip:
            self.stdout.write("Set the IP of %s to %s" % (name, ip))
        elif clear_ip:
            self.stdout.write("Cleared the IP of %s" % name)
        self._write_client(client)
        if key:
            self.stdout.write("Key: %s" % key)
            self.stdout.write(
                "Save the key to the client's key file; it can't be shown again."
            )

    def _list(self):
        clients = models.Client.objects.filter(build_key_hash__isnull=False)
        for client in clients.order_by("name").prefetch_related("build_users__server"):
            self._write_client(client)

    def _write_client(self, client):
        users = ", ".join(
            sorted("%s:%s" % (u.server.name, u.name) for u in client.build_users.all())
        )
        ip = client.ip if client.ip else "not pinned"
        self.stdout.write("%s: build users: %s; IP: %s" % (client.name, users, ip))

    def _get_ip(self, options):
        ip = options.get("ip")
        if ip is None:
            return None
        try:
            return str(ipaddress.ip_address(ip))
        except ValueError:
            raise CommandError("Invalid IP address: %s" % ip)

    def _get_build_user(self, value):
        """
        Input:
          value[str]: <server>:<user>
        Return:
          models.GitUser: the user
        """
        server_name, _, user_name = value.rpartition(":")
        if not server_name or not user_name:
            raise CommandError(
                "Invalid build user, should be <server>:<user>: %s" % value
            )
        try:
            return models.GitUser.objects.get(name=user_name, server__name=server_name)
        except models.GitUser.DoesNotExist:
            raise CommandError("No user %s on server %s" % (user_name, server_name))

    def _get_registered(self, name):
        try:
            return models.Client.objects.get(name=name, build_key_hash__isnull=False)
        except models.Client.DoesNotExist:
            raise CommandError("No registered client named %s" % name)

    def _create(self, name, new):
        """
        Gets the client to register with the name. An old client that isn't
        registered is used if it is the only one with the name, so that its
        history is kept. Its address is cleared, since it was never checked.
        Return:
          models.Client: the client, not saved yet if it is new
        """
        clients = models.Client.objects.filter(name=name)
        if clients.filter(build_key_hash__isnull=False).exists():
            raise CommandError(
                "%s is already registered; use --update or --rotate" % name
            )
        old_clients = list(clients)
        if new or not old_clients:
            return models.Client(name=name)
        if len(old_clients) > 1:
            raise CommandError(
                "%s old clients are named %s; use --new to register a new one"
                % (len(old_clients), name)
            )
        client = old_clients[0]
        client.ip = None
        self.stdout.write("Using the old client %s (%s)" % (name, client.pk))
        return client
