from django.contrib.auth import get_user_model
from django.db import models

from baserow.core.mixins import (
    CreatedAndUpdatedOnMixin,
    HierarchicalModelMixin,
    ParentWorkspaceTrashableModelMixin,
)
from baserow.core.models import Workspace

from .parquet.writer import COLUMN_NAMING_FIELD_ID, COLUMN_NAMINGS

User = get_user_model()

MODE_AUTO = "auto"
MODE_FULL = "full"
MODE_INCREMENTAL = "incremental"
MODES = (MODE_AUTO, MODE_FULL, MODE_INCREMENTAL)

RUN_STATE_RUNNING = "running"
RUN_STATE_FINISHED = "finished"
RUN_STATE_FAILED = "failed"


class TableExportSchedule(
    CreatedAndUpdatedOnMixin,
    HierarchicalModelMixin,
    ParentWorkspaceTrashableModelMixin,
    models.Model,
):
    """
    A recurring Parquet export of the rows of some or all tables of a database to a
    datalake destination. A periodic task picks up every schedule whose `next_run_on`
    has passed and exports each table on behalf of `user`.
    """

    name = models.CharField(
        max_length=100, help_text="The human readable name of the schedule."
    )
    workspace = models.ForeignKey(
        Workspace,
        on_delete=models.CASCADE,
        related_name="+",
        help_text="The workspace the database belongs to.",
    )
    database = models.ForeignKey(
        "database.Database",
        on_delete=models.CASCADE,
        related_name="+",
        help_text="The database whose tables are exported.",
    )
    table_ids = models.JSONField(
        null=True,
        blank=True,
        default=None,
        help_text="The tables to export. Null means every table of the database.",
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="+",
        help_text="The user the exports run on behalf of.",
    )
    destination = models.CharField(
        max_length=100,
        help_text="The name of the env-declared data destination to write to.",
    )
    cron = models.CharField(
        max_length=100,
        help_text=(
            "A five field crontab expression (minute hour day_of_month month "
            "day_of_week) describing when the export runs."
        ),
    )
    timezone = models.CharField(
        max_length=64,
        default="UTC",
        help_text="The timezone the cron expression is evaluated in.",
    )
    full_every_n = models.PositiveIntegerField(
        default=24,
        help_text=(
            "Force a full export after this many incremental ones. Zero only exports "
            "fully when required, for example after a schema change."
        ),
    )
    column_naming = models.CharField(
        max_length=16,
        choices=[(naming, naming) for naming in COLUMN_NAMINGS],
        default=COLUMN_NAMING_FIELD_ID,
        help_text=(
            "How Parquet columns are named: `field_id` (stable across renames) or "
            "`field_name`."
        ),
    )
    is_active = models.BooleanField(
        default=True, help_text="Inactive schedules are skipped by the periodic task."
    )
    next_run_on = models.DateTimeField(
        db_index=True, help_text="The next moment this schedule is due."
    )
    last_run_on = models.DateTimeField(
        null=True, blank=True, help_text="The last moment this schedule ran."
    )
    last_error = models.TextField(
        blank=True,
        default="",
        help_text="The errors of the last run, empty when it was fine.",
    )

    class Meta:
        ordering = ("id",)

    def get_parent(self):
        return self.workspace


class TableExportState(models.Model):
    """The incremental export watermark of one table of a schedule."""

    schedule = models.ForeignKey(
        TableExportSchedule, on_delete=models.CASCADE, related_name="states"
    )
    table = models.ForeignKey(
        "database.Table", on_delete=models.CASCADE, related_name="+"
    )
    last_watermark = models.DateTimeField(
        null=True,
        blank=True,
        help_text="The snapshot moment of the last successful export.",
    )
    last_full_on = models.DateTimeField(null=True, blank=True)
    incrementals_since_full = models.PositiveIntegerField(default=0)
    schema_fingerprint = models.CharField(max_length=64, blank=True, default="")

    class Meta:
        unique_together = ("schedule", "table")


class TableExportRun(models.Model):
    """The history of the exports of a schedule, one entry per table per run."""

    schedule = models.ForeignKey(
        TableExportSchedule, on_delete=models.CASCADE, related_name="runs"
    )
    table = models.ForeignKey(
        "database.Table",
        null=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    mode = models.CharField(max_length=16)
    state = models.CharField(max_length=16, default=RUN_STATE_RUNNING)
    snapshot_at = models.DateTimeField(null=True, blank=True)
    watermark_from = models.DateTimeField(null=True, blank=True)
    watermark_to = models.DateTimeField(null=True, blank=True)
    row_count = models.BigIntegerField(default=0)
    object_prefix = models.CharField(max_length=1024, blank=True, default="")
    warnings = models.JSONField(default=list, blank=True)
    error = models.TextField(blank=True, default="")
    started_on = models.DateTimeField(auto_now_add=True)
    finished_on = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-id",)
