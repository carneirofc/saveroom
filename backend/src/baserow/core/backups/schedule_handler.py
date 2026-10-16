from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import List, Optional

from django.contrib.auth.models import AbstractUser
from django.db.models import QuerySet
from django.utils import timezone

from celery.schedules import crontab

from baserow.core.data_destinations.config import PURPOSE_BACKUP
from baserow.core.data_destinations.handler import DataDestinationHandler
from baserow.core.exceptions import ApplicationDoesNotExist
from baserow.core.handler import CoreHandler
from baserow.core.import_export.handler import ImportExportHandler
from baserow.core.models import Application, ExportApplicationsJob, Workspace
from baserow.core.operations import ListApplicationsWorkspaceOperationType
from baserow.core.scheduling import cron as cron_utils
from baserow.core.scheduling.ownership import can_manage_schedule

from .exceptions import (
    BackupScheduleDoesNotExist,
    BackupScheduleNotOwned,
    InvalidBackupScheduleCron,
)
from .handler import BackupHandler
from .models import BackupSchedule, ExportApplicationsToDestinationJob
from .operations import (
    CreateBackupScheduleOperationType,
    DeleteBackupScheduleOperationType,
    ListBackupSchedulesOperationType,
    ReadBackupScheduleOperationType,
    UpdateBackupScheduleOperationType,
)


@contextmanager
def _as_backup_schedule_error():
    """
    Re-raises a generic cron error as `InvalidBackupScheduleCron`, so the backup API
    keeps its own error code.
    """

    try:
        yield
    except InvalidBackupScheduleCron:
        raise
    except cron_utils.InvalidCron as exc:
        raise InvalidBackupScheduleCron(str(exc)) from exc


class BackupScheduleHandler:
    def parse_cron(self, expression: str) -> crontab:
        """
        Turns a five field cron expression into a celery crontab schedule.

        :param expression: A `minute hour day_of_month month day_of_week` expression.
        :raises InvalidBackupScheduleCron: When the expression cannot be parsed.
        :return: The parsed schedule.
        """

        with _as_backup_schedule_error():
            return cron_utils.parse_cron(expression)

    def validate_timezone(self, name: str) -> str:
        """
        Checks that the given timezone name is known.

        :param name: An IANA timezone name.
        :raises InvalidBackupScheduleCron: When the timezone is unknown.
        :return: The validated name.
        """

        with _as_backup_schedule_error():
            return cron_utils.validate_timezone(name)

    def compute_next_run_on(
        self,
        cron: str,
        tz_name: str = "UTC",
        after: Optional[datetime] = None,
    ) -> datetime:
        """
        Computes the first moment the cron expression is due after the given moment.

        :param cron: The cron expression.
        :param tz_name: The timezone the expression is evaluated in.
        :param after: The moment to start from, defaults to now. The returned moment
            is always strictly after it.
        :raises InvalidBackupScheduleCron: When the expression never matches.
        :return: The next due moment, as an aware UTC datetime.
        """

        with _as_backup_schedule_error():
            return cron_utils.compute_next_run_on(cron, tz_name, after)

    def list_schedules(self, user: AbstractUser, workspace_id: int) -> QuerySet:
        """
        Lists the backup schedules of a workspace.

        :param user: The user on whose behalf the schedules are listed.
        :param workspace_id: The workspace to list the schedules of.
        :return: A queryset of backup schedules.
        """

        workspace = CoreHandler().get_workspace(workspace_id)
        CoreHandler().check_permissions(
            user,
            ListBackupSchedulesOperationType.type,
            workspace=workspace,
            context=workspace,
        )

        return BackupSchedule.objects.filter(workspace=workspace).select_related(
            "workspace", "user"
        )

    def get_schedule(
        self, user: AbstractUser, schedule_id: int, for_update: bool = False
    ) -> BackupSchedule:
        """
        Fetches a single backup schedule.

        :param user: The user on whose behalf the schedule is requested.
        :param schedule_id: The id of the requested schedule.
        :param for_update: Whether the row should be locked.
        :raises BackupScheduleDoesNotExist: When the schedule does not exist.
        :return: The fetched schedule.
        """

        queryset = BackupSchedule.objects.select_related("workspace", "user")

        if for_update:
            queryset = queryset.select_for_update(of=("self",))

        try:
            schedule = queryset.get(id=schedule_id)
        except BackupSchedule.DoesNotExist:
            raise BackupScheduleDoesNotExist(
                f"The backup schedule with id {schedule_id} does not exist."
            )

        CoreHandler().check_permissions(
            user,
            ReadBackupScheduleOperationType.type,
            workspace=schedule.workspace,
            context=schedule,
        )

        return schedule

    def create_schedule(
        self,
        user: AbstractUser,
        workspace: Workspace,
        name: str,
        cron: str,
        tz_name: str = "UTC",
        application_ids: Optional[List[int]] = None,
        only_structure: bool = False,
        keep_last: Optional[int] = None,
        keep_days: Optional[int] = None,
        is_active: bool = True,
        destination: str = "",
    ) -> BackupSchedule:
        """
        Creates a new backup schedule for a workspace.

        :param user: The user on whose behalf the scheduled backups will run.
        :param workspace: The workspace to back up.
        :param name: The human readable name of the schedule.
        :param cron: The cron expression describing when the backup runs.
        :param tz_name: The timezone the cron expression is evaluated in.
        :param application_ids: The applications to back up, None means all of them.
        :param only_structure: If true the row data is left out of the archive.
        :param destination: The data destination every backup is uploaded to, empty
            keeps the backups on the instance storage only.
        :param keep_last: Count based retention, None disables it.
        :param keep_days: Age based retention in days, None disables it.
        :param is_active: Whether the schedule runs.
        :return: The created schedule.
        """

        CoreHandler().check_permissions(
            user,
            CreateBackupScheduleOperationType.type,
            workspace=workspace,
            context=workspace,
        )

        tz_name = self.validate_timezone(tz_name)
        self._validate_destination(destination)
        self._validate_application_ids(user, workspace, application_ids)

        return BackupSchedule.objects.create(
            name=name,
            workspace=workspace,
            user=user,
            cron=cron,
            timezone=tz_name,
            application_ids=application_ids,
            only_structure=only_structure,
            destination=destination,
            keep_last=keep_last,
            keep_days=keep_days,
            is_active=is_active,
            next_run_on=self.compute_next_run_on(cron, tz_name),
        )

    def update_schedule(
        self, user: AbstractUser, schedule: BackupSchedule, **values
    ) -> BackupSchedule:
        """
        Updates an existing backup schedule. Only the provided fields are changed.

        :param user: The user on whose behalf the schedule is updated.
        :param schedule: The schedule to update.
        :param values: The fields to change.
        :return: The updated schedule.
        """

        CoreHandler().check_permissions(
            user,
            UpdateBackupScheduleOperationType.type,
            workspace=schedule.workspace,
            context=schedule,
        )
        self._check_owner_or_admin(user, schedule)

        allowed = [
            "name",
            "cron",
            "timezone",
            "application_ids",
            "only_structure",
            "destination",
            "keep_last",
            "keep_days",
            "is_active",
        ]

        for field in allowed:
            if field in values:
                setattr(schedule, field, values[field])

        schedule.timezone = self.validate_timezone(schedule.timezone)
        if "application_ids" in values:
            # The backups run as the owner, who must be able to see every application.
            self._validate_application_ids(
                schedule.user, schedule.workspace, schedule.application_ids
            )
        if "destination" in values:
            self._validate_destination(schedule.destination)

        if "cron" in values or "timezone" in values or values.get("is_active"):
            schedule.next_run_on = self.compute_next_run_on(
                schedule.cron, schedule.timezone
            )

        schedule.save()
        return schedule

    def delete_schedule(self, user: AbstractUser, schedule: BackupSchedule):
        """
        Deletes a backup schedule. Backups it already made are kept.

        :param user: The user on whose behalf the schedule is deleted.
        :param schedule: The schedule to delete.
        """

        CoreHandler().check_permissions(
            user,
            DeleteBackupScheduleOperationType.type,
            workspace=schedule.workspace,
            context=schedule,
        )
        self._check_owner_or_admin(user, schedule)

        schedule.delete()

    def run_schedule(
        self, schedule: BackupSchedule, requested_by: Optional[AbstractUser] = None
    ) -> ExportApplicationsJob:
        """
        Starts the backup of a schedule right now, on behalf of the schedule's user.

        This does not advance `next_run_on`, the periodic task owns that.

        :param schedule: The schedule to run.
        :param requested_by: The user asking for the run, when it is triggered
            manually. Because the backup itself runs as the schedule's own user,
            triggering one requires permission to change the schedule, not merely to
            read it: the owner, a workspace admin or staff. Leave it out for the periodic task.
        :return: The started export job.
        """

        if requested_by is not None:
            CoreHandler().check_permissions(
                requested_by,
                UpdateBackupScheduleOperationType.type,
                workspace=schedule.workspace,
                context=schedule,
            )
            self._check_owner_or_admin(requested_by, schedule)

        return BackupHandler().start_backup(
            schedule.user,
            schedule.workspace_id,
            application_ids=schedule.application_ids,
            only_structure=schedule.only_structure,
            destination=schedule.destination or None,
            backup_schedule=schedule,
        )

    def _check_owner_or_admin(self, user: AbstractUser, schedule: BackupSchedule):
        """
        :raises BackupScheduleNotOwned: When the user is neither the owner of the
            schedule, an admin of its workspace nor staff.
        """

        if not can_manage_schedule(user, schedule):
            raise BackupScheduleNotOwned()

    def _validate_application_ids(
        self,
        user: AbstractUser,
        workspace: Workspace,
        application_ids: Optional[List[int]],
    ):
        """
        Checks that every application belongs to the workspace and is visible to the
        user the backups run as.

        :raises ApplicationDoesNotExist: When one of them is not.
        """

        if not application_ids:
            return

        requested = set(application_ids)
        applications = Application.objects.filter(
            workspace=workspace, workspace__trashed=False, id__in=requested
        )
        applications = CoreHandler().filter_queryset(
            user,
            ListApplicationsWorkspaceOperationType.type,
            applications,
            workspace=workspace,
        )

        if applications.count() != len(requested):
            raise ApplicationDoesNotExist(
                "Some of the applications do not exist in the workspace or the owner "
                "of the schedule cannot access them."
            )

    def _validate_destination(self, destination: str):
        """
        Checks that a non-empty destination is configured and meant for backups.

        :raises DataDestinationDoesNotExist: When it is not configured.
        :raises DataDestinationPurposeNotAllowed: When it is not meant for backups.
        """

        if destination:
            DataDestinationHandler().get_destination(
                destination, purpose=PURPOSE_BACKUP
            )

    def apply_retention(self, schedule: BackupSchedule) -> int:
        """
        Marks the backups made by a schedule that fall outside its retention window
        for deletion.

        Retention only ever considers the backups the schedule itself started, so
        manual backups and the backups of other schedules are never removed by it.
        Backups made before scheduled backups recorded their schedule are left alone.

        :param schedule: The schedule whose retention rules are applied.
        :return: The number of backups marked for deletion.
        """

        if schedule.keep_last is None and schedule.keep_days is None:
            return 0

        backups = list(
            ExportApplicationsToDestinationJob.objects.filter(
                backup_schedule=schedule,
                workspace_id=schedule.workspace_id,
                user_id=schedule.user_id,
                resource__is_valid=True,
                resource__marked_for_deletion=False,
            )
            .select_related("resource")
            # Ids follow creation order, `updated_on` moves whenever a job is touched.
            .order_by("-id")
        )

        to_delete = []

        if schedule.keep_last is not None:
            to_delete.extend(backups[schedule.keep_last :])

        if schedule.keep_days is not None:
            cutoff = timezone.now() - timedelta(days=schedule.keep_days)
            to_delete.extend(backup for backup in backups if backup.updated_on < cutoff)

        import_export_handler = ImportExportHandler()
        deleted_resource_ids = set()

        for backup in to_delete:
            if backup.resource_id in deleted_resource_ids:
                continue
            try:
                import_export_handler.mark_resource_for_deletion(
                    schedule.user, backup.resource_id
                )
                deleted_resource_ids.add(backup.resource_id)
            except Exception:
                # A resource that is currently being imported cannot be removed yet.
                # The next run of the schedule will try again.
                continue

        return len(deleted_resource_ids)
