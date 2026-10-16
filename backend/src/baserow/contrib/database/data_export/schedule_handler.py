from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import List, Optional

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import transaction
from django.db.models import QuerySet

from baserow.contrib.database.export.operations import ExportTableOperationType
from baserow.contrib.database.table.models import Table
from baserow.core.data_destinations.config import PURPOSE_DATALAKE
from baserow.core.data_destinations.handler import DataDestinationHandler
from baserow.core.exceptions import PermissionDenied
from baserow.core.handler import CoreHandler
from baserow.core.scheduling import cron as cron_utils
from baserow.core.scheduling.ownership import can_manage_schedule

from .exceptions import (
    InvalidTableExportScheduleCron,
    TableExportScheduleDoesNotExist,
    TableExportTablesNotInDatabase,
)
from .models import MODE_AUTO, TableExportRun, TableExportSchedule, TableExportState
from .operations import (
    CreateTableExportScheduleOperationType,
    DeleteTableExportScheduleOperationType,
    ListTableExportSchedulesOperationType,
    ReadTableExportScheduleOperationType,
    UpdateTableExportScheduleOperationType,
)

UPDATABLE_FIELDS = [
    "name",
    "cron",
    "timezone",
    "destination",
    "table_ids",
    "full_every_n",
    "column_naming",
    "is_active",
]


@contextmanager
def _as_schedule_cron_error():
    try:
        yield
    except InvalidTableExportScheduleCron:
        raise
    except cron_utils.InvalidCron as exc:
        raise InvalidTableExportScheduleCron(str(exc)) from exc


class TableExportScheduleHandler:
    def compute_next_run_on(
        self, cron: str, tz_name: str = "UTC", after: Optional[datetime] = None
    ) -> datetime:
        with _as_schedule_cron_error():
            return cron_utils.compute_next_run_on(cron, tz_name, after)

    def get_warnings(self, schedule: TableExportSchedule) -> List[str]:
        """
        Warns when consecutive runs are further apart than the trash retention, which
        forces every export to be full.
        """

        try:
            first = self.compute_next_run_on(schedule.cron, schedule.timezone)
            second = self.compute_next_run_on(
                schedule.cron, schedule.timezone, after=first
            )
        except InvalidTableExportScheduleCron:
            return []

        retention = timedelta(hours=settings.HOURS_UNTIL_TRASH_PERMANENTLY_DELETED)
        if second - first > retention:
            return [
                "The schedule runs less often than trashed rows are permanently "
                "deleted, so every export will be full instead of incremental."
            ]
        return []

    def _validate(
        self,
        user: AbstractUser,
        schedule: TableExportSchedule,
    ):
        with _as_schedule_cron_error():
            cron_utils.validate_timezone(schedule.timezone)

        DataDestinationHandler().get_destination(
            schedule.destination, purpose=PURPOSE_DATALAKE
        )

        tables = Table.objects.filter(database_id=schedule.database_id)
        if schedule.table_ids is not None:
            requested = set(schedule.table_ids)
            tables = list(tables.filter(id__in=requested))
            if len(tables) != len(requested):
                raise TableExportTablesNotInDatabase(
                    "Some of the tables do not exist in the database of the schedule."
                )

        # The exports run as this user, who must be allowed to export every table.
        for table in tables:
            CoreHandler().check_permissions(
                user,
                ExportTableOperationType.type,
                workspace=schedule.workspace,
                context=table,
            )

    def list_schedules(self, user: AbstractUser, workspace_id: int) -> QuerySet:
        workspace = CoreHandler().get_workspace(workspace_id)
        CoreHandler().check_permissions(
            user,
            ListTableExportSchedulesOperationType.type,
            workspace=workspace,
            context=workspace,
        )
        return TableExportSchedule.objects.filter(workspace=workspace).select_related(
            "workspace", "database", "user"
        )

    def get_schedule(
        self, user: AbstractUser, schedule_id: int, for_update: bool = False
    ) -> TableExportSchedule:
        queryset = TableExportSchedule.objects.select_related(
            "workspace", "database", "user"
        )
        if for_update:
            queryset = queryset.select_for_update(of=("self",))

        try:
            schedule = queryset.get(id=schedule_id)
        except TableExportSchedule.DoesNotExist:
            raise TableExportScheduleDoesNotExist(
                f"The table export schedule with id {schedule_id} does not exist."
            )

        CoreHandler().check_permissions(
            user,
            ReadTableExportScheduleOperationType.type,
            workspace=schedule.workspace,
            context=schedule,
        )
        return schedule

    def create_schedule(
        self,
        user: AbstractUser,
        database,
        name: str,
        cron: str,
        destination: str,
        tz_name: str = "UTC",
        table_ids: Optional[List[int]] = None,
        full_every_n: int = 24,
        column_naming: str = "field_id",
        is_active: bool = True,
    ) -> TableExportSchedule:
        workspace = database.workspace
        CoreHandler().check_permissions(
            user,
            CreateTableExportScheduleOperationType.type,
            workspace=workspace,
            context=workspace,
        )

        schedule = TableExportSchedule(
            name=name,
            workspace=workspace,
            database=database,
            user=user,
            destination=destination,
            cron=cron,
            timezone=tz_name,
            table_ids=table_ids,
            full_every_n=full_every_n,
            column_naming=column_naming,
            is_active=is_active,
        )
        self._validate(user, schedule)
        schedule.next_run_on = self.compute_next_run_on(cron, tz_name)
        schedule.save()
        return schedule

    def update_schedule(
        self, user: AbstractUser, schedule: TableExportSchedule, **values
    ) -> TableExportSchedule:
        CoreHandler().check_permissions(
            user,
            UpdateTableExportScheduleOperationType.type,
            workspace=schedule.workspace,
            context=schedule,
        )

        for field in UPDATABLE_FIELDS:
            if field in values:
                setattr(schedule, field, values[field])

        # The updating user becomes the one the exports run as, so a member can
        # never make a schedule export tables with somebody else's permissions.
        schedule.user = user
        self._validate(user, schedule)

        if "cron" in values or "timezone" in values or values.get("is_active"):
            schedule.next_run_on = self.compute_next_run_on(
                schedule.cron, schedule.timezone
            )

        if "column_naming" in values or "table_ids" in values:
            # Earlier runs no longer line up with the new layout.
            TableExportState.objects.filter(schedule=schedule).delete()

        schedule.save()
        return schedule

    def delete_schedule(self, user: AbstractUser, schedule: TableExportSchedule):
        CoreHandler().check_permissions(
            user,
            DeleteTableExportScheduleOperationType.type,
            workspace=schedule.workspace,
            context=schedule,
        )
        schedule.delete()

    def run_schedule(
        self,
        user: AbstractUser,
        schedule: TableExportSchedule,
        mode: str = MODE_AUTO,
    ):
        """
        Queues an export of the schedule right now, without changing when it next
        runs. Requires permission to change the schedule, because the export runs
        with the permissions of the schedule's user.
        """

        from .tasks import run_table_export_schedule

        CoreHandler().check_permissions(
            user,
            UpdateTableExportScheduleOperationType.type,
            workspace=schedule.workspace,
            context=schedule,
        )
        if not can_manage_schedule(user, schedule):
            raise PermissionDenied()

        schedule_id = schedule.id
        transaction.on_commit(
            lambda: run_table_export_schedule.delay(schedule_id, mode)
        )

    def reset_state(self, user: AbstractUser, schedule: TableExportSchedule) -> int:
        """Forgets the watermarks, so the next export of every table is full."""

        CoreHandler().check_permissions(
            user,
            UpdateTableExportScheduleOperationType.type,
            workspace=schedule.workspace,
            context=schedule,
        )
        deleted, _ = TableExportState.objects.filter(schedule=schedule).delete()
        return deleted

    def list_runs(self, user: AbstractUser, schedule: TableExportSchedule) -> QuerySet:
        CoreHandler().check_permissions(
            user,
            ReadTableExportScheduleOperationType.type,
            workspace=schedule.workspace,
            context=schedule,
        )
        return TableExportRun.objects.filter(schedule=schedule).select_related("table")
