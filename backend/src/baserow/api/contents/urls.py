from django.urls import re_path

from .views import ApplicationContentsView, WorkspaceContentsView

app_name = "baserow.api.contents"

urlpatterns = [
    re_path(
        r"^workspace/(?P<workspace_id>[0-9]+)/$",
        WorkspaceContentsView.as_view(),
        name="workspace",
    ),
    re_path(
        r"^application/(?P<application_id>[0-9]+)/$",
        ApplicationContentsView.as_view(),
        name="application",
    ),
]
