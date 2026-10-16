from django.db import transaction

from drf_spectacular.openapi import OpenApiParameter, OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from baserow.api.decorators import map_exceptions, validate_body
from baserow.api.errors import (
    ERROR_USER_INVALID_GROUP_PERMISSIONS,
    ERROR_USER_NOT_IN_GROUP,
)
from baserow.api.schemas import get_error_schema
from baserow.contrib.database.access.exceptions import (
    InvalidAccessScope,
    InvalidAccessSubject,
)
from baserow.contrib.database.access.handler import SCOPE_TYPES, AccessScope
from baserow.contrib.database.access.service import DatabaseAccessService
from baserow.core.exceptions import (
    UserInvalidWorkspacePermissionsError,
    UserNotInWorkspace,
)
from baserow.core.models import WORKSPACE_USER_PERMISSION_ADMIN

from .errors import ERROR_ACCESS_SCOPE_DOES_NOT_EXIST, ERROR_INVALID_ACCESS_SUBJECT
from .serializers import ScopeAccessSerializer, SetGrantsSerializer

EXCEPTIONS = {
    InvalidAccessScope: ERROR_ACCESS_SCOPE_DOES_NOT_EXIST,
    InvalidAccessSubject: ERROR_INVALID_ACCESS_SUBJECT,
    UserNotInWorkspace: ERROR_USER_NOT_IN_GROUP,
    UserInvalidWorkspacePermissionsError: ERROR_USER_INVALID_GROUP_PERMISSIONS,
}
PARAMETERS = [
    OpenApiParameter(
        name="scope_type",
        location=OpenApiParameter.PATH,
        type=OpenApiTypes.STR,
        enum=SCOPE_TYPES,
        description="What the access applies to: the workspace default, a database "
        "or a table.",
    ),
    OpenApiParameter(
        name="scope_id",
        location=OpenApiParameter.PATH,
        type=OpenApiTypes.INT,
        description="The id of the workspace, database or table.",
    ),
]


def serialize_scope_access(service: DatabaseAccessService, scope: AccessScope):
    handler = service.handler
    grants = handler.get_scope_grants(scope)
    inherited = handler.get_inherited_grants(scope)
    members, teams = handler.list_subjects(scope.workspace)

    def subject(subject_type, subject_id, name, email, is_admin):
        inherited_level, inherited_from = inherited.get(
            (subject_type, subject_id), (None, None)
        )
        return {
            "subject_type": subject_type,
            "subject_id": subject_id,
            "name": name,
            "email": email,
            "is_admin": is_admin,
            "level": grants.get((subject_type, subject_id)),
            "inherited_level": inherited_level,
            "inherited_from": inherited_from,
        }

    scope_object = scope.table or scope.database or scope.workspace
    return ScopeAccessSerializer(
        {
            "scope_type": scope.type,
            "scope_id": scope_object.id,
            "workspace_id": scope.workspace.id,
            "subjects": [
                subject("team", team.id, team.name, None, False) for team in teams
            ]
            + [
                subject(
                    "user",
                    member.user_id,
                    member.user.first_name or member.user.email,
                    member.user.email,
                    member.permissions == WORKSPACE_USER_PERMISSION_ADMIN,
                )
                for member in members
            ],
        }
    ).data


class DatabaseAccessView(APIView):
    permission_classes = (IsAuthenticated,)

    @extend_schema(
        parameters=PARAMETERS,
        tags=["Database access"],
        operation_id="get_database_access",
        description=(
            "Lists the members and teams of the workspace with their access level "
            "on the scope and the level they inherit from a parent scope. Requires "
            "workspace admin or staff."
        ),
        responses={
            200: ScopeAccessSerializer,
            400: get_error_schema(
                ["ERROR_USER_NOT_IN_GROUP", "ERROR_USER_INVALID_GROUP_PERMISSIONS"]
            ),
            404: get_error_schema(["ERROR_ACCESS_SCOPE_DOES_NOT_EXIST"]),
        },
    )
    @map_exceptions(EXCEPTIONS)
    def get(self, request, scope_type, scope_id):
        service = DatabaseAccessService()
        scope = service.get_scope(request.user, scope_type, scope_id)
        return Response(serialize_scope_access(service, scope))

    @extend_schema(
        parameters=PARAMETERS,
        tags=["Database access"],
        operation_id="set_database_access",
        description=(
            "Sets the access level of members and teams on the scope. A null level "
            "removes the grant so the subject inherits again. Workspace admins are "
            "never restricted. Requires workspace admin or staff."
        ),
        request=SetGrantsSerializer,
        responses={
            200: ScopeAccessSerializer,
            400: get_error_schema(
                [
                    "ERROR_USER_NOT_IN_GROUP",
                    "ERROR_USER_INVALID_GROUP_PERMISSIONS",
                    "ERROR_INVALID_ACCESS_SUBJECT",
                    "ERROR_REQUEST_BODY_VALIDATION",
                ]
            ),
            404: get_error_schema(["ERROR_ACCESS_SCOPE_DOES_NOT_EXIST"]),
        },
    )
    @transaction.atomic
    @validate_body(SetGrantsSerializer)
    @map_exceptions(EXCEPTIONS)
    def put(self, request, data, scope_type, scope_id):
        service = DatabaseAccessService()
        scope = service.get_scope(request.user, scope_type, scope_id)
        service.set_grants(request.user, scope, data["grants"])
        return Response(serialize_scope_access(service, scope))
