from django.urls import re_path

from .views import (
    BackupDownloadView,
    BackupSchedulesView,
    BackupScheduleView,
    BackupsView,
    BackupView,
    RemoteBackupsView,
    RestoreBackupView,
    RestoreRemoteBackupView,
    RunBackupScheduleView,
    StartBackupView,
)

app_name = "baserow.api.backups"

urlpatterns = [
    re_path(
        r"^destinations/(?P<destination>[A-Za-z0-9_-]+)/workspace/"
        r"(?P<workspace_id>[0-9]+)/restore/$",
        RestoreRemoteBackupView.as_view(),
        name="remote_restore",
    ),
    re_path(
        r"^destinations/(?P<destination>[A-Za-z0-9_-]+)/workspace/"
        r"(?P<workspace_id>[0-9]+)/$",
        RemoteBackupsView.as_view(),
        name="remote_list",
    ),
    re_path(
        r"^schedules/workspace/(?P<workspace_id>[0-9]+)/$",
        BackupSchedulesView.as_view(),
        name="schedule_list",
    ),
    re_path(
        r"^schedules/(?P<schedule_id>[0-9]+)/run/$",
        RunBackupScheduleView.as_view(),
        name="schedule_run",
    ),
    re_path(
        r"^schedules/(?P<schedule_id>[0-9]+)/$",
        BackupScheduleView.as_view(),
        name="schedule_item",
    ),
    re_path(
        r"^workspace/(?P<workspace_id>[0-9]+)/restore/$",
        RestoreBackupView.as_view(),
        name="restore",
    ),
    re_path(
        r"^workspace/(?P<workspace_id>[0-9]+)/(?P<resource_id>[0-9]+)/download/$",
        BackupDownloadView.as_view(),
        name="download",
    ),
    re_path(
        r"^workspace/(?P<workspace_id>[0-9]+)/(?P<resource_id>[0-9]+)/$",
        BackupView.as_view(),
        name="item",
    ),
    re_path(
        r"^workspace/(?P<workspace_id>[0-9]+)/async/$",
        StartBackupView.as_view(),
        name="start",
    ),
    re_path(
        r"^workspace/(?P<workspace_id>[0-9]+)/$",
        BackupsView.as_view(),
        name="list",
    ),
]
