import json

from django.core.management.base import BaseCommand

from baserow.core.backups.destination import BackupDestinationHandler


class Command(BaseCommand):
    help = (
        "Lists the backups uploaded to an env-declared data destination, most recent "
        "first, as one JSON document per line. Pass a key to `restore_from_destination` "
        "to restore it."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--destination",
            required=True,
            help="The name of the data destination to list.",
        )
        parser.add_argument(
            "--workspace-id",
            type=int,
            help="Only list the backups made of this workspace.",
        )

    def handle(self, *args, **options):
        backups = BackupDestinationHandler().list_backups(
            options["destination"], options["workspace_id"]
        )

        for backup in backups:
            self.stdout.write(
                json.dumps(
                    {
                        "key": backup["key"],
                        "created_on": backup.get("created_on"),
                        "workspace": backup.get("workspace"),
                        "applications": backup.get("applications"),
                        "only_structure": backup.get("only_structure"),
                        "size": backup.get("size"),
                        "instance_id": backup.get("instance_id"),
                    }
                )
            )
