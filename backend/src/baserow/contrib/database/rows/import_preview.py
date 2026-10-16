from typing import Any, Optional

from django.contrib.auth.models import AbstractUser
from django.db import transaction

from baserow.contrib.database.table.models import Table
from baserow.contrib.database.table.operations import (
    ImportRowsDatabaseTableOperationType,
    ReplaceRowsDatabaseTableOperationType,
)
from baserow.core.handler import CoreHandler

from .constants import is_destructive_import
from .exceptions import CannotCreateRowsInTable
from .handler import RowHandler
from .import_planner import ImportPlanner
from .types import FileImportConfiguration


class TableImportPreviewHandler:
    """
    Previews what a file import into an existing table would change, using the same
    `ImportPlanner` as the import itself.
    """

    def preview(
        self,
        user: AbstractUser,
        table: Table,
        data: list[list[Any]],
        configuration: Optional[FileImportConfiguration] = None,
        sample_size: int = 50,
    ) -> dict[str, Any]:
        """
        :param user: The user on whose behalf the import would run.
        :param table: The table the data would be imported into.
        :param data: The imported rows, one value per writable field.
        :param configuration: The import configuration.
        :param sample_size: The maximum number of rows returned per kind of change.
        :raises CannotCreateRowsInTable: When the table is a read only synced table.
        :raises PermissionDenied: When the user can't apply the import.
        :return: The summary, the ambiguous keys and samples of the changes.
        """

        from baserow.contrib.database.api.rows.serializers import (
            RowSerializer,
            get_row_serializer_class,
        )

        if table.is_read_only_data_synced_table:
            raise CannotCreateRowsInTable(
                "Can't create rows because it has a data sync."
            )

        core_handler = CoreHandler()
        core_handler.check_permissions(
            user,
            ImportRowsDatabaseTableOperationType.type,
            workspace=table.database.workspace,
            context=table,
        )
        # A user who may not trash rows may not enumerate the rows that would be
        # trashed either.
        if is_destructive_import(configuration):
            core_handler.check_permissions(
                user,
                ReplaceRowsDatabaseTableOperationType.type,
                workspace=table.database.workspace,
                context=table,
            )

        model = table.get_model()
        # Nothing is written, the transaction only keeps the temp tables used to
        # match rows on a single connection.
        with transaction.atomic():
            plan = ImportPlanner(
                user,
                table,
                data,
                configuration=configuration,
                model=model,
                raise_on_ambiguity=False,
            ).plan()
        RowHandler().check_import_permissions(user, table, plan)

        update_sample = plan.to_update[:sample_size]
        delete_sample = plan.to_delete_ids[:sample_size]
        serializer_class = get_row_serializer_class(
            model, RowSerializer, is_response=True
        )
        rows_by_id = {
            row.id: serializer_class(row).data
            for row in model.objects.filter(
                id__in=[planned.row_id for planned in update_sample] + delete_sample
            ).enhance_by_fields()
        }

        return {
            "summary": plan.summary(),
            "ambiguous_blocked": plan.ambiguous_blocked,
            "ambiguous": plan.ambiguous,
            "create": [import_idx for import_idx, _ in plan.to_create[:sample_size]],
            "update": [
                {
                    "import_index": planned.import_index,
                    "row": rows_by_id[planned.row_id],
                    "changed_field_ids": planned.changed_field_ids,
                }
                for planned in update_sample
                if planned.row_id in rows_by_id
            ],
            "delete": [
                rows_by_id[row_id] for row_id in delete_sample if row_id in rows_by_id
            ],
            "skipped": plan.skipped[:sample_size],
            "errors": {
                index: error
                for index, error in list(plan.error_report.to_dict().items())[
                    :sample_size
                ]
            },
        }
