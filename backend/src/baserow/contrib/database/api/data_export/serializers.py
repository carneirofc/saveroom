from typing import List

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from baserow.contrib.database.data_export.models import (
    MODE_AUTO,
    MODES,
    TableExportRun,
    TableExportSchedule,
)
from baserow.contrib.database.data_export.parquet.writer import (
    COLUMN_NAMING_FIELD_ID,
    COLUMN_NAMINGS,
)
from baserow.contrib.database.data_export.schedule_handler import (
    TableExportScheduleHandler,
)

CRON_HELP = (
    "A five field crontab expression: minute, hour, day_of_month, month_of_year, "
    "day_of_week. For example `0 * * * *` runs every hour."
)


class TableExportScheduleSerializer(serializers.ModelSerializer):
    user_id = serializers.IntegerField(
        read_only=True,
        help_text="The user the schedule runs as, who can manage it.",
    )
    warnings = serializers.SerializerMethodField(
        help_text="Configuration problems worth knowing about, for example a cron "
        "expression that runs less often than trashed rows are deleted."
    )

    class Meta:
        model = TableExportSchedule
        fields = (
            "id",
            "name",
            "workspace",
            "user_id",
            "database",
            "table_ids",
            "destination",
            "cron",
            "timezone",
            "full_every_n",
            "column_naming",
            "is_active",
            "next_run_on",
            "last_run_on",
            "last_error",
            "created_on",
            "updated_on",
            "warnings",
        )
        read_only_fields = fields

    @extend_schema_field(serializers.ListField(child=serializers.CharField()))
    def get_warnings(self, schedule: TableExportSchedule) -> List[str]:
        return TableExportScheduleHandler().get_warnings(schedule)


class CreateTableExportScheduleSerializer(serializers.Serializer):
    database_id = serializers.IntegerField(
        help_text="The database whose tables are exported."
    )
    name = serializers.CharField(max_length=100)
    cron = serializers.CharField(max_length=100, help_text=CRON_HELP)
    destination = serializers.CharField(
        max_length=100,
        help_text="The name of a data destination declared for the `datalake` purpose.",
    )
    timezone = serializers.CharField(max_length=64, required=False, default="UTC")
    table_ids = serializers.ListField(
        child=serializers.IntegerField(),
        required=False,
        allow_null=True,
        allow_empty=False,
        default=None,
        help_text="The tables to export. Leave it out to export every table.",
    )
    full_every_n = serializers.IntegerField(
        min_value=0,
        required=False,
        default=24,
        help_text=(
            "Force a full export after this many incremental ones. Zero only exports "
            "fully when required."
        ),
    )
    column_naming = serializers.ChoiceField(
        choices=COLUMN_NAMINGS, required=False, default=COLUMN_NAMING_FIELD_ID
    )
    is_active = serializers.BooleanField(required=False, default=True)


class UpdateTableExportScheduleSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=100, required=False)
    cron = serializers.CharField(max_length=100, required=False, help_text=CRON_HELP)
    destination = serializers.CharField(max_length=100, required=False)
    timezone = serializers.CharField(max_length=64, required=False)
    table_ids = serializers.ListField(
        child=serializers.IntegerField(),
        required=False,
        allow_null=True,
        allow_empty=False,
    )
    full_every_n = serializers.IntegerField(min_value=0, required=False)
    column_naming = serializers.ChoiceField(choices=COLUMN_NAMINGS, required=False)
    is_active = serializers.BooleanField(required=False)


class RunTableExportScheduleSerializer(serializers.Serializer):
    mode = serializers.ChoiceField(
        choices=MODES,
        required=False,
        default=MODE_AUTO,
        help_text=(
            "`auto` exports incrementally when possible, `full` always exports every "
            "row."
        ),
    )


class TableExportRunSerializer(serializers.ModelSerializer):
    table_id = serializers.IntegerField(allow_null=True)
    warnings = serializers.ListField(child=serializers.CharField())

    class Meta:
        model = TableExportRun
        fields = (
            "id",
            "table_id",
            "mode",
            "state",
            "snapshot_at",
            "watermark_from",
            "watermark_to",
            "row_count",
            "object_prefix",
            "warnings",
            "error",
            "started_on",
            "finished_on",
        )
        read_only_fields = fields


@extend_schema_field(OpenApiTypes.OBJECT)
class RunQueuedSerializer(serializers.Serializer):
    schedule_id = serializers.IntegerField()
    mode = serializers.CharField()
