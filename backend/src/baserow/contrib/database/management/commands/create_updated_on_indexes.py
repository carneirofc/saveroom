from django.core.management.base import BaseCommand
from django.db import connection

from baserow.contrib.database.table.models import Table


class Command(BaseCommand):
    help = (
        "Creates an index on the `updated_on` column of table rows, concurrently and "
        "only where missing. Incremental datalake exports select changed rows by "
        "that column, which otherwise scans the whole table."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--table-id",
            type=int,
            action="append",
            dest="table_ids",
            help="Only index this table. Can be repeated. All tables by default.",
        )

    def handle(self, *args, **options):
        tables = Table.objects.all().order_by("id")
        if options["table_ids"]:
            tables = tables.filter(id__in=options["table_ids"])

        quote = connection.ops.quote_name
        for table in tables.iterator():
            table_name = table.get_database_table_name()
            index_name = f"{table_name}_updated_on_idx"
            # CONCURRENTLY cannot run inside a transaction block, and does not lock
            # out writes while the index builds.
            with connection.cursor() as cursor:
                cursor.execute(
                    f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {quote(index_name)} "
                    f"ON {quote(table_name)} (updated_on)"
                )
            self.stdout.write(f"Indexed updated_on of table {table.id}.")
