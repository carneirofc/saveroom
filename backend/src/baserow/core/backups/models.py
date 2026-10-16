from django.contrib.auth import get_user_model
from django.db import models

from baserow.core.mixins import (
    CreatedAndUpdatedOnMixin,
    HierarchicalModelMixin,
    ParentWorkspaceTrashableModelMixin,
)
from baserow.core.models import ExportApplicationsJob, Workspace

User = get_user_model()


class BackupSchedule(
    CreatedAndUpdatedOnMixin,
    HierarchicalModelMixin,
    ParentWorkspaceTrashableModelMixin,
    models.Model,
):
    """
    A recurring backup of a workspace or of a subset of its applications. A periodic
    task picks up every schedule whose `next_run_on` has passed and starts the regular
    application export job on behalf of `user`.
    """

    name = models.CharField(
        max_length=100,
        help_text="The human readable name of the schedule.",
    )
    workspace = models.ForeignKey(
        Workspace,
        on_delete=models.CASCADE,
        related_name="backup_schedules",
        help_text="The workspace that is backed up.",
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        help_text="The user the scheduled backups are performed on behalf of.",
    )
    cron = models.CharField(
        max_length=100,
        help_text=(
            "A five field crontab expression (minute hour day_of_month month "
            "day_of_week) describing when the backup runs."
        ),
    )
    timezone = models.CharField(
        max_length=64,
        default="UTC",
        help_text="The timezone the cron expression is evaluated in.",
    )
    application_ids = models.JSONField(
        null=True,
        blank=True,
        default=None,
        help_text=(
            "The applications to back up. Null means every application of the "
            "workspace."
        ),
    )
    only_structure = models.BooleanField(
        default=False,
        help_text="If true the backup contains the structure but not the row data.",
    )
    destination = models.CharField(
        max_length=100,
        blank=True,
        default="",
        help_text=(
            "The name of the env-declared data destination the backups are also "
            "shipped to. Empty keeps them on the instance storage only."
        ),
    )
    keep_last = models.PositiveIntegerField(
        null=True,
        blank=True,
        default=None,
        help_text=(
            "Only keep this many of the most recent backups made by this schedule. "
            "Null disables count based retention."
        ),
    )
    keep_days = models.PositiveIntegerField(
        null=True,
        blank=True,
        default=None,
        help_text=(
            "Delete backups made by this schedule that are older than this many days. "
            "Null disables age based retention."
        ),
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Inactive schedules are skipped by the periodic task.",
    )
    next_run_on = models.DateTimeField(
        db_index=True,
        help_text="The next moment this schedule is due.",
    )
    last_run_on = models.DateTimeField(
        null=True,
        blank=True,
        help_text="The last moment this schedule started a backup.",
    )
    last_error = models.TextField(
        blank=True,
        default="",
        help_text="The error of the last failed run, empty when the last run was fine.",
    )

    class Meta:
        ordering = ("id",)

    def get_parent(self):
        return self.workspace


class ExportApplicationsToDestinationJob(ExportApplicationsJob):
    """
    A regular application export whose archive is also uploaded to an external data
    destination. Inheriting from `ExportApplicationsJob` keeps it visible to the
    existing backup listing and retention logic.
    """

    destination = models.CharField(
        max_length=100,
        help_text="The name of the data destination the archive is uploaded to.",
    )
    backup_schedule = models.ForeignKey(
        BackupSchedule,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        help_text="The schedule that started the backup, if any.",
    )
    remote_key = models.CharField(
        max_length=512,
        blank=True,
        default="",
        help_text="The key of the uploaded archive, relative to the destination prefix.",
    )
