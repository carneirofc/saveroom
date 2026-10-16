from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from baserow.core.auth_provider.models import OIDCAuthProviderModel
from baserow.core.sso.oidc.config import get_oidc_provider
from baserow.core.sso.oidc.provider import OIDCAuthProviderType
from baserow.core.user.utils import normalize_email_address

User = get_user_model()


class Command(BaseCommand):
    help = (
        "Break-glass management of the links between Saveroom accounts and the "
        "env-configured OIDC providers. Use it to recover accounts refused with "
        "errorDifferentProvider, including staff accounts that are never linked "
        "automatically, or to carry every link over after renaming a provider."
    )

    def add_arguments(self, parser):
        subparsers = parser.add_subparsers(
            dest="action", help="Action to perform (list, link, unlink)"
        )

        list_parser = subparsers.add_parser(
            "list", help="List the authentication providers an account is linked to."
        )
        list_parser.add_argument("email", type=str, help="The account's email.")

        link_parser = subparsers.add_parser(
            "link", help="Link accounts to an OIDC provider."
        )
        link_parser.add_argument(
            "provider_name",
            type=str,
            help="The provider 'name' in BASEROW_OIDC_PROVIDERS.",
        )
        source = link_parser.add_mutually_exclusive_group(required=True)
        source.add_argument(
            "--email",
            action="append",
            dest="emails",
            help="An account email to link. Can be repeated.",
        )
        source.add_argument(
            "--from-provider",
            type=str,
            help="Link every account linked to this (old) OIDC provider name.",
        )

        unlink_parser = subparsers.add_parser(
            "unlink", help="Unlink accounts from an OIDC provider."
        )
        unlink_parser.add_argument(
            "provider_name", type=str, help="The OIDC provider name."
        )
        unlink_parser.add_argument(
            "--email",
            action="append",
            dest="emails",
            required=True,
            help="An account email to unlink. Can be repeated.",
        )

    def handle(self, *args, **options):
        action = options.get("action")

        if action == "list":
            self._list(options["email"])
        elif action == "link":
            self._link(
                options["provider_name"], options["emails"], options["from_provider"]
            )
        elif action == "unlink":
            self._unlink(options["provider_name"], options["emails"])
        else:
            raise CommandError("Invalid action. Use 'list', 'link', or 'unlink'.")

    def _get_user(self, email):
        try:
            return User.objects.get(username=normalize_email_address(email))
        except User.DoesNotExist:
            raise CommandError(f"No account with the email '{email}' exists.")

    def _list(self, email):
        user = self._get_user(email)
        providers = user.auth_providers.all().order_by("id")
        if not providers:
            self.stdout.write(f"'{user.email}' is not linked to any provider.")
        for provider in providers:
            specific = provider.specific
            name = getattr(specific, "name", "")
            label = f"{specific.get_type().type} {name}".strip()
            self.stdout.write(f"{user.email}: {label}")

    @transaction.atomic
    def _link(self, provider_name, emails, from_provider):
        config = get_oidc_provider(provider_name)
        if config is None:
            raise CommandError(
                f"No OIDC provider named '{provider_name}' is configured in "
                f"BASEROW_OIDC_PROVIDERS."
            )
        provider = OIDCAuthProviderType.get_or_create_provider_model(config)

        if from_provider is not None:
            try:
                source = OIDCAuthProviderModel.objects.get(name=from_provider)
            except OIDCAuthProviderModel.DoesNotExist:
                raise CommandError(f"No OIDC provider named '{from_provider}' exists.")
            users = list(source.users.all())
        else:
            users = [self._get_user(email) for email in emails]

        for user in users:
            provider.users.add(user)
            self.stdout.write(
                self.style.SUCCESS(f"Linked '{user.email}' to '{provider_name}'.")
            )

    @transaction.atomic
    def _unlink(self, provider_name, emails):
        try:
            provider = OIDCAuthProviderModel.objects.get(name=provider_name)
        except OIDCAuthProviderModel.DoesNotExist:
            raise CommandError(f"No OIDC provider named '{provider_name}' exists.")

        for email in emails:
            user = self._get_user(email)
            provider.users.remove(user)
            self.stdout.write(
                self.style.SUCCESS(f"Unlinked '{user.email}' from '{provider_name}'.")
            )
