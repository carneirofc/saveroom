import hashlib
import tempfile
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from django.conf import settings
from django.core.files.base import ContentFile
from django.db import connection
from django.utils import timezone

from loguru import logger

from baserow.contrib.database.export.operations import ExportTableOperationType
from baserow.contrib.database.table.models import Table
from baserow.core.data_destinations.config import PURPOSE_DATALAKE
from baserow.core.data_destinations.handler import DataDestinationHandler
from baserow.core.db import IsolationLevel, transaction_atomic
from baserow.core.handler import CoreHandler
from baserow.version import VERSION

from .exceptions import TableExportAlreadyRunning
from .models import (
    MODE_AUTO,
    MODE_FULL,
    MODE_INCREMENTAL,
    RUN_STATE_FAILED,
    RUN_STATE_FINISHED,
    RUN_STATE_RUNNING,
    TableExportRun,
    TableExportSchedule,
    TableExportState,
)
from .parquet.writer import (
    BASE_COLUMNS,
    ParquetPart,
    TableParquetWriter,
    build_columns,
    schema_fingerprint,
)

MANIFEST_FORMAT_VERSION = 1
TABLES_PREFIX = "tables"


def _advisory_lock_key(schedule_id: int, table_id: int) -> int:
    digest = hashlib.sha256(
        f"baserow:table_export:{schedule_id}:{table_id}".encode()
    ).digest()
    return int.from_bytes(digest[:8], "big", signed=True)


def _iso(value: Optional[datetime]) -> Optional[str]:
    return value.isoformat() if value else None


class TableExportHandler:
    """
    Exports the rows of tables to Parquet files on a datalake destination.

    Every run of a table is published under
    `tables/workspace=<id>/database=<id>/table=<id>/schedule=<id>/mode=<mode>/run=<ts>_<id>/`
    as part files, a `_manifest.json` and finally an empty `_SUCCESS` marker. A
    consumer must ignore a run without `_SUCCESS`.

    A full run holds every row, trashed rows flagged with `_deleted`, and replaces
    the table in the lake. An incremental run holds the rows whose `updated_on` moved
    since the last run, overlapping it slightly to catch late commits, and is merged
    by `id`, keeping the highest `updated_on`.
    """

    def __init__(self):
        self.destinations = DataDestinationHandler()

    def get_tables(self, schedule: TableExportSchedule) -> List[Table]:
        tables = Table.objects.filter(database_id=schedule.database_id)
        if schedule.table_ids is not None:
            tables = tables.filter(id__in=schedule.table_ids)
        return list(tables.select_related("database__workspace").order_by("id"))

    def get_table_prefix(self, schedule: TableExportSchedule, table: Table) -> str:
        return (
            f"{TABLES_PREFIX}/workspace={schedule.workspace_id}/"
            f"database={table.database_id}/table={table.id}/schedule={schedule.id}"
        )

    def decide_mode(
        self,
        schedule: TableExportSchedule,
        state: TableExportState,
        fingerprint: str,
        requested_mode: str,
        snapshot_at: datetime,
    ) -> Tuple[str, List[str], List[str]]:
        """
        Decides whether a run is full or incremental. An incremental run is only
        possible when it can be merged correctly with the earlier runs.

        :return: The mode, the reasons a full run was chosen, and warnings.
        """

        reasons: List[str] = []
        warnings: List[str] = []
        retention = timedelta(hours=settings.HOURS_UNTIL_TRASH_PERMANENTLY_DELETED)

        if requested_mode == MODE_FULL:
            reasons.append("A full export was requested.")
        if state.last_watermark is None:
            reasons.append("The table was never exported before.")
        elif state.schema_fingerprint != fingerprint:
            reasons.append("The exported fields of the table changed.")
        elif schedule.full_every_n and (
            state.incrementals_since_full >= schedule.full_every_n
        ):
            reasons.append(
                f"{schedule.full_every_n} incremental exports ran since the last full."
            )
        elif snapshot_at - state.last_watermark > retention:
            reasons.append("The last export is older than the trash retention.")
            warnings.append(
                "Rows permanently deleted since the last export cannot be reported as "
                "deleted, so this export is full. Export more often than "
                "HOURS_UNTIL_TRASH_PERMANENTLY_DELETED to keep incremental exports."
            )

        if reasons:
            return MODE_FULL, reasons, warnings
        return MODE_INCREMENTAL, reasons, warnings

    def export_schedule(
        self,
        schedule: TableExportSchedule,
        mode: str = MODE_AUTO,
        table_ids: Optional[List[int]] = None,
    ) -> Tuple[List[TableExportRun], List[str]]:
        """
        Exports every table of a schedule. A failing table does not stop the others.

        :param schedule: The schedule to run.
        :param mode: `auto`, `full` or `incremental`. Incremental still falls back to
            full when it cannot be merged correctly.
        :param table_ids: Only export these tables of the schedule.
        :return: The runs that were made, and the error of every failed table.
        """

        runs: List[TableExportRun] = []
        errors: List[str] = []

        for table in self.get_tables(schedule):
            if table_ids and table.id not in table_ids:
                continue
            try:
                runs.append(self.export_table(schedule, table, mode))
            except TableExportAlreadyRunning:
                logger.info(
                    "Skipping table {table_id} of export schedule {schedule_id}, an "
                    "export is already running.",
                    table_id=table.id,
                    schedule_id=schedule.id,
                )
            except Exception as exc:  # noqa: BLE001 - recorded per table
                logger.error(
                    "Export of table {table_id} of schedule {schedule_id} failed: "
                    "{error}",
                    table_id=table.id,
                    schedule_id=schedule.id,
                    error=exc,
                )
                errors.append(f"Table {table.id}: {exc}")

        return runs, errors

    def export_table(
        self, schedule: TableExportSchedule, table: Table, mode: str = MODE_AUTO
    ) -> TableExportRun:
        """
        Exports one table of a schedule and publishes it on the destination.

        :raises TableExportAlreadyRunning: When the table is being exported already.
        :return: The finished run. A failed run is recorded before re-raising.
        """

        run = TableExportRun.objects.create(
            schedule=schedule, table=table, mode=mode, state=RUN_STATE_RUNNING
        )

        try:
            CoreHandler().check_permissions(
                schedule.user,
                ExportTableOperationType.type,
                workspace=table.database.workspace,
                context=table,
            )
            destination = self.destinations.get_destination(
                schedule.destination, purpose=PURPOSE_DATALAKE
            )
            storage = self.destinations.get_storage(destination)
            state, _ = TableExportState.objects.get_or_create(
                schedule=schedule, table=table
            )

            with tempfile.TemporaryDirectory(
                dir=settings.BASEROW_DATA_EXPORT_TMP_DIR
            ) as directory:
                snapshot = self._write_snapshot(schedule, table, state, mode, directory)
                prefix = self._publish(storage, schedule, table, run, snapshot)
        except TableExportAlreadyRunning:
            run.delete()
            raise
        except Exception as exc:
            run.state = RUN_STATE_FAILED
            run.error = str(exc) or exc.__class__.__name__
            run.finished_on = timezone.now()
            run.save()
            raise

        snapshot_at = snapshot["snapshot_at"]
        state.last_watermark = snapshot_at
        state.schema_fingerprint = snapshot["fingerprint"]
        if snapshot["mode"] == MODE_FULL:
            state.last_full_on = snapshot_at
            state.incrementals_since_full = 0
        else:
            state.incrementals_since_full += 1
        state.save()

        run.mode = snapshot["mode"]
        run.state = RUN_STATE_FINISHED
        run.snapshot_at = snapshot_at
        run.watermark_from = snapshot["watermark_from"]
        run.watermark_to = snapshot_at
        run.row_count = sum(part.rows for part in snapshot["parts"])
        run.object_prefix = prefix
        run.warnings = snapshot["warnings"]
        run.finished_on = timezone.now()
        run.save()

        return run

    def _write_snapshot(
        self,
        schedule: TableExportSchedule,
        table: Table,
        state: TableExportState,
        mode: str,
        directory: str,
    ) -> Dict[str, Any]:
        """
        Writes the rows to local part files from one consistent snapshot of the
        database. Uploading happens afterwards, so the snapshot is not kept open for
        the duration of a slow upload.
        """

        # A repeatable read transaction must be the outermost one. When already
        # inside a transaction, such as in tests, its snapshot is used as is.
        isolation_level = (
            None if connection.in_atomic_block else IsolationLevel.REPEATABLE_READ
        )

        with transaction_atomic(isolation_level=isolation_level):
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT pg_try_advisory_xact_lock(%s)",
                    [_advisory_lock_key(schedule.id, table.id)],
                )
                if not cursor.fetchone()[0]:
                    raise TableExportAlreadyRunning(
                        f"Table {table.id} of schedule {schedule.id} is already being "
                        f"exported."
                    )

            # Taken before the rows are read: a row committed with an older
            # `updated_on` after this moment is picked up by the overlap of the next
            # incremental export.
            snapshot_at = timezone.now()

            model = table.get_model()
            columns = build_columns(model, schedule.column_naming)
            fingerprint = schema_fingerprint(columns, schedule.column_naming)
            effective_mode, reasons, warnings = self.decide_mode(
                schedule, state, fingerprint, mode, snapshot_at
            )

            queryset = model.objects_and_trash.all().enhance_by_fields()
            watermark_from = None
            if effective_mode == MODE_INCREMENTAL:
                watermark_from = state.last_watermark - timedelta(
                    seconds=settings.BASEROW_DATA_EXPORT_WATERMARK_OVERLAP_SECONDS
                )
                queryset = queryset.filter(
                    updated_on__gt=watermark_from, updated_on__lte=snapshot_at
                )

            run_id = uuid.uuid4().hex
            parts = TableParquetWriter(
                columns,
                directory,
                run_id=run_id,
                extracted_at=snapshot_at,
                chunk_size=settings.BASEROW_DATA_EXPORT_CHUNK_SIZE,
                max_rows_per_file=settings.BASEROW_DATA_EXPORT_MAX_ROWS_PER_FILE,
            ).write(queryset)

        return {
            "run_id": run_id,
            "snapshot_at": snapshot_at,
            "mode": effective_mode,
            "reasons": reasons,
            "warnings": warnings,
            "watermark_from": watermark_from,
            "fingerprint": fingerprint,
            "columns": columns,
            "parts": parts,
        }

    def _publish(
        self,
        storage,
        schedule: TableExportSchedule,
        table: Table,
        run: TableExportRun,
        snapshot: Dict[str, Any],
    ) -> str:
        """
        Uploads the part files, then the manifest, then the `_SUCCESS` marker.

        :return: The key prefix of the run.
        """

        snapshot_at = snapshot["snapshot_at"]
        mode = snapshot["mode"]
        table_prefix = self.get_table_prefix(schedule, table)
        timestamp = snapshot_at.strftime("%Y%m%dT%H%M%SZ")
        prefix = f"{table_prefix}/mode={mode}/run={timestamp}_{snapshot['run_id']}"

        parts: List[ParquetPart] = snapshot["parts"]
        files = []
        for part in parts:
            key = f"{prefix}/{part.file_name}"
            with open(part.path, "rb") as handle:
                self.destinations.save_file(storage, key, handle)
            files.append(
                {
                    "key": key,
                    "rows": part.rows,
                    "size": part.size,
                    "sha256": part.sha256,
                }
            )

        workspace = table.database.workspace
        manifest = {
            "format_version": MANIFEST_FORMAT_VERSION,
            "run_id": snapshot["run_id"],
            "mode": mode,
            # A full export replaces the table, an incremental one is merged into it.
            "semantics": "replace" if mode == MODE_FULL else "upsert",
            "merge": {
                "key": "id",
                "version_column": "updated_on",
                "delete_column": "_deleted",
            },
            "reasons": snapshot["reasons"],
            "warnings": snapshot["warnings"],
            "instance_id": CoreHandler().get_settings().instance_id,
            "baserow_version": VERSION,
            "schedule_id": schedule.id,
            "workspace": {"id": workspace.id, "name": workspace.name},
            "database": {"id": table.database_id, "name": table.database.name},
            "table": {"id": table.id, "name": table.name},
            "snapshot_at": _iso(snapshot_at),
            "watermark_from": _iso(snapshot["watermark_from"]),
            "watermark_to": _iso(snapshot_at),
            "row_count": sum(part.rows for part in parts),
            "column_naming": schedule.column_naming,
            "schema_fingerprint": snapshot["fingerprint"],
            "base_columns": [
                {"column": column.name, "arrow_type": str(column.type)}
                for column in BASE_COLUMNS
            ],
            "columns": [column.describe() for column in snapshot["columns"]],
            "files": files,
        }

        self.destinations.write_json(storage, f"{prefix}/_manifest.json", manifest)
        self.destinations.save_file(storage, f"{prefix}/_SUCCESS", ContentFile(b""))
        self.destinations.write_json(
            storage,
            f"{table_prefix}/_state/latest.json",
            {
                "run_id": snapshot["run_id"],
                "mode": mode,
                "prefix": prefix,
                "snapshot_at": _iso(snapshot_at),
                "schema_fingerprint": snapshot["fingerprint"],
                "local_run_id": run.id,
            },
        )

        return prefix
