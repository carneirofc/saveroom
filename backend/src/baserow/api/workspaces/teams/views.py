from django.db import transaction

from drf_spectacular.openapi import OpenApiParameter, OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from baserow.api.decorators import map_exceptions, validate_body
from baserow.api.errors import (
    ERROR_GROUP_DOES_NOT_EXIST,
    ERROR_USER_INVALID_GROUP_PERMISSIONS,
    ERROR_USER_NOT_IN_GROUP,
)
from baserow.api.schemas import get_error_schema
from baserow.core.exceptions import (
    UserInvalidWorkspacePermissionsError,
    UserNotInWorkspace,
    WorkspaceDoesNotExist,
)
from baserow.core.handler import CoreHandler
from baserow.core.teams.exceptions import (
    TeamDoesNotExist,
    TeamMemberNotInWorkspace,
    TeamNameNotUnique,
)
from baserow.core.teams.service import TeamService

from .errors import (
    ERROR_TEAM_DOES_NOT_EXIST,
    ERROR_TEAM_MEMBER_NOT_IN_WORKSPACE,
    ERROR_TEAM_NAME_NOT_UNIQUE,
)
from .serializers import (
    CreateTeamSerializer,
    TeamMembersSerializer,
    TeamSerializer,
    UpdateTeamSerializer,
)

COMMON_EXCEPTIONS = {
    WorkspaceDoesNotExist: ERROR_GROUP_DOES_NOT_EXIST,
    UserNotInWorkspace: ERROR_USER_NOT_IN_GROUP,
    UserInvalidWorkspacePermissionsError: ERROR_USER_INVALID_GROUP_PERMISSIONS,
    TeamDoesNotExist: ERROR_TEAM_DOES_NOT_EXIST,
    TeamNameNotUnique: ERROR_TEAM_NAME_NOT_UNIQUE,
    TeamMemberNotInWorkspace: ERROR_TEAM_MEMBER_NOT_IN_WORKSPACE,
}
COMMON_ERRORS_400 = get_error_schema(
    [
        "ERROR_USER_NOT_IN_GROUP",
        "ERROR_USER_INVALID_GROUP_PERMISSIONS",
        "ERROR_TEAM_NAME_NOT_UNIQUE",
        "ERROR_TEAM_MEMBER_NOT_IN_WORKSPACE",
        "ERROR_REQUEST_BODY_VALIDATION",
    ]
)


def _serialize(team):
    return TeamSerializer(
        TeamService().handler.list_teams(team.workspace).get(id=team.id)
    ).data


class WorkspaceTeamsView(APIView):
    permission_classes = (IsAuthenticated,)

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="workspace_id",
                location=OpenApiParameter.PATH,
                type=OpenApiTypes.INT,
                description="Lists the teams of this workspace.",
            )
        ],
        tags=["Workspace teams"],
        operation_id="list_workspace_teams",
        description="Lists the teams of the workspace. Requires workspace admin.",
        responses={
            200: TeamSerializer(many=True),
            400: COMMON_ERRORS_400,
            404: get_error_schema(["ERROR_GROUP_DOES_NOT_EXIST"]),
        },
    )
    @map_exceptions(COMMON_EXCEPTIONS)
    def get(self, request, workspace_id):
        workspace = CoreHandler().get_workspace(workspace_id)
        teams = TeamService().list_teams(request.user, workspace)
        return Response(TeamSerializer(teams, many=True).data)

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="workspace_id",
                location=OpenApiParameter.PATH,
                type=OpenApiTypes.INT,
                description="Creates a team in this workspace.",
            )
        ],
        tags=["Workspace teams"],
        operation_id="create_workspace_team",
        description="Creates a team, optionally with initial members.",
        request=CreateTeamSerializer,
        responses={
            200: TeamSerializer,
            400: COMMON_ERRORS_400,
            404: get_error_schema(["ERROR_GROUP_DOES_NOT_EXIST"]),
        },
    )
    @transaction.atomic
    @validate_body(CreateTeamSerializer)
    @map_exceptions(COMMON_EXCEPTIONS)
    def post(self, request, data, workspace_id):
        workspace = CoreHandler().get_workspace(workspace_id)
        team = TeamService().create_team(
            request.user, workspace, data["name"], data["user_ids"]
        )
        return Response(_serialize(team))


class TeamView(APIView):
    permission_classes = (IsAuthenticated,)

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="team_id",
                location=OpenApiParameter.PATH,
                type=OpenApiTypes.INT,
                description="Renames this team.",
            )
        ],
        tags=["Workspace teams"],
        operation_id="update_workspace_team",
        description="Renames a team.",
        request=UpdateTeamSerializer,
        responses={
            200: TeamSerializer,
            400: COMMON_ERRORS_400,
            404: get_error_schema(["ERROR_TEAM_DOES_NOT_EXIST"]),
        },
    )
    @transaction.atomic
    @validate_body(UpdateTeamSerializer)
    @map_exceptions(COMMON_EXCEPTIONS)
    def patch(self, request, data, team_id):
        service = TeamService()
        team = service.handler.get_team(team_id)
        team = service.update_team(request.user, team, data["name"])
        return Response(_serialize(team))

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="team_id",
                location=OpenApiParameter.PATH,
                type=OpenApiTypes.INT,
                description="Deletes this team.",
            )
        ],
        tags=["Workspace teams"],
        operation_id="delete_workspace_team",
        description="Deletes a team and every access grant given to it.",
        responses={
            204: None,
            400: COMMON_ERRORS_400,
            404: get_error_schema(["ERROR_TEAM_DOES_NOT_EXIST"]),
        },
    )
    @transaction.atomic
    @map_exceptions(COMMON_EXCEPTIONS)
    def delete(self, request, team_id):
        service = TeamService()
        team = service.handler.get_team(team_id)
        service.delete_team(request.user, team)
        return Response(status=204)


class TeamMembersView(APIView):
    permission_classes = (IsAuthenticated,)

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="team_id",
                location=OpenApiParameter.PATH,
                type=OpenApiTypes.INT,
                description="Adds members to this team.",
            )
        ],
        tags=["Workspace teams"],
        operation_id="add_workspace_team_members",
        description="Adds workspace members to the team.",
        request=TeamMembersSerializer,
        responses={
            200: TeamSerializer,
            400: COMMON_ERRORS_400,
            404: get_error_schema(["ERROR_TEAM_DOES_NOT_EXIST"]),
        },
    )
    @transaction.atomic
    @validate_body(TeamMembersSerializer)
    @map_exceptions(COMMON_EXCEPTIONS)
    def post(self, request, data, team_id):
        service = TeamService()
        team = service.handler.get_team(team_id)
        service.add_members(request.user, team, data["user_ids"])
        return Response(_serialize(team))

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="team_id",
                location=OpenApiParameter.PATH,
                type=OpenApiTypes.INT,
                description="Removes members from this team.",
            )
        ],
        tags=["Workspace teams"],
        operation_id="remove_workspace_team_members",
        description="Removes members from the team.",
        request=TeamMembersSerializer,
        responses={
            200: TeamSerializer,
            400: COMMON_ERRORS_400,
            404: get_error_schema(["ERROR_TEAM_DOES_NOT_EXIST"]),
        },
    )
    @transaction.atomic
    @validate_body(TeamMembersSerializer)
    @map_exceptions(COMMON_EXCEPTIONS)
    def delete(self, request, data, team_id):
        service = TeamService()
        team = service.handler.get_team(team_id)
        service.remove_members(request.user, team, data["user_ids"])
        return Response(_serialize(team))
