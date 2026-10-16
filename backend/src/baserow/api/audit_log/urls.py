from django.urls import re_path

from .views import (
    AuditLogEntryAdminView,
    AuditLogEntryExportView,
    AuditLogEntryFilterOptionsView,
)

app_name = "baserow.api.audit_log"

urlpatterns = [
    re_path(r"^export/$", AuditLogEntryExportView.as_view(), name="export"),
    re_path(
        r"^filter-options/$",
        AuditLogEntryFilterOptionsView.as_view(),
        name="filter_options",
    ),
    re_path(r"^$", AuditLogEntryAdminView.as_view(), name="list"),
]
