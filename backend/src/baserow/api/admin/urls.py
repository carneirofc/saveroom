from django.urls import include, path

from baserow.api.audit_log import urls as audit_log_urls

from .backups import urls as backups_urls
from .build import urls as build_urls
from .dashboard import urls as dashboard_urls
from .limits import urls as limits_urls
from .users import urls as users_urls
from .workspaces import urls as workspaces_urls

app_name = "baserow.api.admin"

urlpatterns = [
    path("dashboard/", include(dashboard_urls, namespace="dashboard")),
    path("users/", include(users_urls, namespace="users")),
    path("workspaces/", include(workspaces_urls, namespace="workspaces")),
    path("audit-log/", include(audit_log_urls, namespace="audit_log")),
    path("backups/", include(backups_urls, namespace="backups")),
    path("limits/", include(limits_urls, namespace="limits")),
    path("build/", include(build_urls, namespace="build")),
]
