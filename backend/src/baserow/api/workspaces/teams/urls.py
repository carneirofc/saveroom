from django.urls import re_path

from .views import TeamMembersView, TeamView, WorkspaceTeamsView

app_name = "baserow.api.workspaces.teams"

urlpatterns = [
    re_path(
        r"workspace/(?P<workspace_id>[0-9]+)/$",
        WorkspaceTeamsView.as_view(),
        name="list",
    ),
    re_path(r"(?P<team_id>[0-9]+)/$", TeamView.as_view(), name="item"),
    re_path(
        r"(?P<team_id>[0-9]+)/members/$", TeamMembersView.as_view(), name="members"
    ),
]
