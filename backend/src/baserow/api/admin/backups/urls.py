from django.urls import re_path

from .views import (
    BackupAdminView,
    BackupDownloadAdminView,
    BackupsAdminView,
    BackupScheduleAdminView,
    BackupSchedulesAdminView,
    RemoteBackupsAdminView,
    RestoreBackupAdminView,
    RestoreRemoteBackupAdminView,
    RunBackupScheduleAdminView,
    StartBackupAdminView,
)

app_name = "baserow.api.admin.backups"

urlpatterns = [
    re_path(
        r"^destinations/(?P<destination>[A-Za-z0-9_-]+)/workspace/"
        r"(?P<workspace_id>[0-9]+)/restore/$",
        RestoreRemoteBackupAdminView.as_view(),
        name="remote_restore",
    ),
    re_path(
        r"^destinations/(?P<destination>[A-Za-z0-9_-]+)/workspace/"
        r"(?P<workspace_id>[0-9]+)/$",
        RemoteBackupsAdminView.as_view(),
        name="remote_list",
    ),
    re_path(
        r"^schedules/workspace/(?P<workspace_id>[0-9]+)/$",
        BackupSchedulesAdminView.as_view(),
        name="schedule_list",
    ),
    re_path(
        r"^schedules/(?P<schedule_id>[0-9]+)/run/$",
        RunBackupScheduleAdminView.as_view(),
        name="schedule_run",
    ),
    re_path(
        r"^schedules/(?P<schedule_id>[0-9]+)/$",
        BackupScheduleAdminView.as_view(),
        name="schedule_item",
    ),
    re_path(
        r"^workspace/(?P<workspace_id>[0-9]+)/restore/$",
        RestoreBackupAdminView.as_view(),
        name="restore",
    ),
    re_path(
        r"^workspace/(?P<workspace_id>[0-9]+)/(?P<resource_id>[0-9]+)/download/$",
        BackupDownloadAdminView.as_view(),
        name="download",
    ),
    re_path(
        r"^workspace/(?P<workspace_id>[0-9]+)/(?P<resource_id>[0-9]+)/$",
        BackupAdminView.as_view(),
        name="item",
    ),
    re_path(
        r"^workspace/(?P<workspace_id>[0-9]+)/async/$",
        StartBackupAdminView.as_view(),
        name="start",
    ),
    re_path(
        r"^workspace/(?P<workspace_id>[0-9]+)/$",
        BackupsAdminView.as_view(),
        name="list",
    ),
]
