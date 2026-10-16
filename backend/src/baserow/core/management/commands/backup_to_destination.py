import sys

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from baserow.core.backups.handler import BackupHandler
from baserow.core.jobs.constants import JOB_FINISHED

User = get_user_model()


class Command(BaseCommand):
    help = (
        "Backs up a workspace, or some of its applications, and uploads the archive to "
        "an env-declared data destination. The backup runs in this process and is "
        "made on behalf of the given user, who must be allowed to export the "
        "workspace."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "workspace_id", type=int, help="The id of the workspace to back up."
        )
        parser.add_argument(
            "--destination",
            required=True,
            help="The name of the data destination to upload the backup to.",
        )
        parser.add_argument(
            "--user-email",
            required=True,
            help="The email of the user the backup is made on behalf of.",
        )
        parser.add_argument(
            "--application-ids",
            type=int,
            nargs="*",
            help="Only back up these applications. All of them by default.",
        )
        parser.add_argument(
            "--only-structure",
            action="store_true",
            help="Leave the row data out of the backup.",
        )

    def handle(self, *args, **options):
        user = User.objects.filter(email=options["user_email"]).first()
        if user is None:
            self.stderr.write(
                self.style.ERROR(f"No user with email {options['user_email']}.")
            )
            sys.exit(1)

        job = BackupHandler().start_backup(
            user,
            options["workspace_id"],
            application_ids=options["application_ids"] or None,
            only_structure=options["only_structure"],
            destination=options["destination"],
            sync=True,
        )

        if job.state != JOB_FINISHED:
            self.stderr.write(self.style.ERROR(f"The backup failed: {job.error}"))
            sys.exit(1)

        self.stdout.write(
            self.style.SUCCESS(
                f"Backup uploaded to {options['destination']}: {job.remote_key}"
            )
        )
