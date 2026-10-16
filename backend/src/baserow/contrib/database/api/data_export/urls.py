from django.urls import re_path

from .views import (
    ResetTableExportStateView,
    RunTableExportScheduleView,
    TableExportRunsView,
    TableExportSchedulesView,
    TableExportScheduleView,
)

app_name = "baserow.contrib.database.api.data_export"

urlpatterns = [
    re_path(
        r"^schedules/workspace/(?P<workspace_id>[0-9]+)/$",
        TableExportSchedulesView.as_view(),
        name="schedule_list",
    ),
    re_path(
        r"^schedules/(?P<schedule_id>[0-9]+)/run/$",
        RunTableExportScheduleView.as_view(),
        name="schedule_run",
    ),
    re_path(
        r"^schedules/(?P<schedule_id>[0-9]+)/runs/$",
        TableExportRunsView.as_view(),
        name="schedule_runs",
    ),
    re_path(
        r"^schedules/(?P<schedule_id>[0-9]+)/reset-state/$",
        ResetTableExportStateView.as_view(),
        name="schedule_reset_state",
    ),
    re_path(
        r"^schedules/(?P<schedule_id>[0-9]+)/$",
        TableExportScheduleView.as_view(),
        name="schedule_item",
    ),
]
