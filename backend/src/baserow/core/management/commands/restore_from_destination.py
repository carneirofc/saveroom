import sys

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from baserow.core.backups.destination import BackupDestinationHandler
from baserow.core.jobs.constants import JOB_FINISHED

User = get_user_model()


class Command(BaseCommand):
    help = (
        "Downloads a backup from an env-declared data destination and restores it into "
        "a workspace as new applications. Find the key with "
        "`list_destination_backups`. The restore runs in this process on behalf of the "
        "given user."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--destination",
            required=True,
            help="The name of the data destination the backup is stored on.",
        )
        parser.add_argument(
            "--key", required=True, help="The key of the backup archive to restore."
        )
        parser.add_argument(
            "--workspace-id",
            type=int,
            required=True,
            help="The id of the workspace to restore into.",
        )
        parser.add_argument(
            "--user-email",
            required=True,
            help="The email of the user the restore is made on behalf of.",
        )
        parser.add_argument(
            "--application-ids",
            type=int,
            nargs="*",
            help="Only restore these applications from the backup. All by default.",
        )
        parser.add_argument(
            "--trust-public-key",
            action="store_true",
            help=(
                "Trust the key the backup was signed with, needed for a backup made by "
                "another instance. The user must be staff and the destination must set "
                "`allow_trust_public_key`."
            ),
        )

    def handle(self, *args, **options):
        user = User.objects.filter(email=options["user_email"]).first()
        if user is None:
            self.stderr.write(
                self.style.ERROR(f"No user with email {options['user_email']}.")
            )
            sys.exit(1)

        job = BackupDestinationHandler().restore_remote_backup(
            user,
            options["workspace_id"],
            options["destination"],
            options["key"],
            application_ids=options["application_ids"] or None,
            trust_public_key=options["trust_public_key"],
            sync=True,
        )

        if job.state != JOB_FINISHED:
            self.stderr.write(self.style.ERROR(f"The restore failed: {job.error}"))
            sys.exit(1)

        self.stdout.write(
            self.style.SUCCESS(
                f"Backup {options['key']} restored into workspace "
                f"{options['workspace_id']}."
            )
        )
