import sys

from django.core.management.base import BaseCommand

from baserow.contrib.database.data_export.handler import TableExportHandler
from baserow.contrib.database.data_export.models import MODES, TableExportSchedule


class Command(BaseCommand):
    help = (
        "Runs a table export schedule right now, in this process, writing Parquet "
        "files to its data destination. Create an inactive schedule to drive exports "
        "only from this command, for example from an external cron job."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--schedule-id",
            type=int,
            required=True,
            help="The id of the table export schedule to run.",
        )
        parser.add_argument(
            "--table-id",
            type=int,
            action="append",
            dest="table_ids",
            help="Only export this table of the schedule. Can be repeated.",
        )
        parser.add_argument(
            "--mode",
            choices=MODES,
            default="auto",
            help=(
                "`auto` exports incrementally when possible, `full` always exports "
                "every row. `incremental` still exports fully when the earlier "
                "exports cannot be merged with it."
            ),
        )

    def handle(self, *args, **options):
        schedule = (
            TableExportSchedule.objects.filter(id=options["schedule_id"])
            .select_related("workspace", "database", "user")
            .first()
        )
        if schedule is None:
            self.stderr.write(
                self.style.ERROR(
                    f"No table export schedule with id {options['schedule_id']}."
                )
            )
            sys.exit(1)

        runs, errors = TableExportHandler().export_schedule(
            schedule, options["mode"], table_ids=options["table_ids"]
        )

        for run in runs:
            self.stdout.write(
                f"Table {run.table_id}: {run.mode} export of {run.row_count} rows to "
                f"{run.object_prefix}"
            )
        for error in errors:
            self.stderr.write(self.style.ERROR(error))

        schedule.last_error = "\n".join(errors)
        schedule.save(update_fields=["last_error", "updated_on"])

        if errors:
            sys.exit(1)
