import json

from django.http import StreamingHttpResponse

from drf_spectacular.openapi import OpenApiParameter, OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from baserow.api.api_clients.authentication import (
    ApiClientAuthentication,
    HasApiClientScope,
)
from baserow.api.applications.errors import ERROR_APPLICATION_DOES_NOT_EXIST
from baserow.api.decorators import map_exceptions
from baserow.api.errors import ERROR_GROUP_DOES_NOT_EXIST, ERROR_USER_NOT_IN_GROUP
from baserow.api.schemas import get_error_schema
from baserow.core.contents.exceptions import ContentsTooLarge
from baserow.core.contents.handler import ContentsHandler
from baserow.core.exceptions import (
    ApplicationDoesNotExist,
    UserNotInWorkspace,
    WorkspaceDoesNotExist,
)
from baserow.core.models import Application

from .errors import ERROR_CONTENTS_TOO_LARGE

COMMON_EXCEPTIONS = {
    WorkspaceDoesNotExist: ERROR_GROUP_DOES_NOT_EXIST,
    ApplicationDoesNotExist: ERROR_APPLICATION_DOES_NOT_EXIST,
    UserNotInWorkspace: ERROR_USER_NOT_IN_GROUP,
    ContentsTooLarge: ERROR_CONTENTS_TOO_LARGE,
}

EXCLUDE_DATA_PARAMETER = OpenApiParameter(
    name="exclude_data",
    location=OpenApiParameter.QUERY,
    type=OpenApiTypes.BOOL,
    description=(
        "When true only the structure is returned, without any row data. This also "
        "skips the size check, so it always succeeds."
    ),
    required=False,
)

CONTENTS_DESCRIPTION_SUFFIX = (
    "\n\nThe response uses the same serialization the backup archives are built from, "
    "but user files are referenced by name instead of embedded. That makes it a "
    "faithful read of the data, not something you can restore from. Reads are also "
    "not taken under a single consistent snapshot, so concurrent writes may be "
    "partially reflected. Use `/api/backups/` when you need a restorable artifact or "
    "a point in time snapshot.\n\nRequests larger than "
    "`BASEROW_CONTENTS_API_MAX_ROWS` rows are refused with "
    "`ERROR_CONTENTS_TOO_LARGE`, start a backup instead."
)


def _streaming_json_response(payload: dict) -> StreamingHttpResponse:
    """
    Streams the payload instead of building one large string in memory on top of the
    already large dict.
    """

    chunks = json.JSONEncoder(ensure_ascii=False).iterencode(payload)
    return StreamingHttpResponse(
        (chunk.encode("utf-8") for chunk in chunks),
        content_type="application/json",
    )


def _exclude_data_requested(request) -> bool:
    return request.GET.get("exclude_data", "false").lower() in ("true", "1", "yes")


class WorkspaceContentsView(APIView):
    authentication_classes = APIView.authentication_classes + [ApiClientAuthentication]
    permission_classes = (IsAuthenticated, HasApiClientScope)
    api_client_scopes = {"GET": "contents.read"}

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="workspace_id",
                location=OpenApiParameter.PATH,
                type=OpenApiTypes.INT,
                description="The workspace to read.",
                required=True,
            ),
            EXCLUDE_DATA_PARAMETER,
        ],
        tags=["Contents"],
        operation_id="get_workspace_contents",
        description=(
            "Returns the complete contents of a workspace as JSON: every application "
            "the authenticated user may read, with their full structure and row data."
            + CONTENTS_DESCRIPTION_SUFFIX
        ),
        responses={
            200: OpenApiTypes.OBJECT,
            400: get_error_schema(["ERROR_USER_NOT_IN_GROUP"]),
            404: get_error_schema(["ERROR_GROUP_DOES_NOT_EXIST"]),
            413: get_error_schema(["ERROR_CONTENTS_TOO_LARGE"]),
        },
    )
    @map_exceptions(COMMON_EXCEPTIONS)
    def get(self, request, workspace_id: int):
        contents = ContentsHandler().get_workspace_contents(
            request.user, workspace_id, exclude_data=_exclude_data_requested(request)
        )
        return _streaming_json_response(contents)


class ApplicationContentsView(APIView):
    authentication_classes = APIView.authentication_classes + [ApiClientAuthentication]
    permission_classes = (IsAuthenticated, HasApiClientScope)
    api_client_scopes = {"GET": "contents.read"}

    def get_api_client_workspace_id(self, request, application_id=None, **kwargs):
        return (
            Application.objects.filter(id=application_id)
            .values_list("workspace_id", flat=True)
            .first()
        )

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="application_id",
                location=OpenApiParameter.PATH,
                type=OpenApiTypes.INT,
                description="The application to read.",
                required=True,
            ),
            EXCLUDE_DATA_PARAMETER,
        ],
        tags=["Contents"],
        operation_id="get_application_contents",
        description=(
            "Returns the complete contents of a single application as JSON, with its "
            "full structure and row data." + CONTENTS_DESCRIPTION_SUFFIX
        ),
        responses={
            200: OpenApiTypes.OBJECT,
            400: get_error_schema(["ERROR_USER_NOT_IN_GROUP"]),
            404: get_error_schema(["ERROR_APPLICATION_DOES_NOT_EXIST"]),
            413: get_error_schema(["ERROR_CONTENTS_TOO_LARGE"]),
        },
    )
    @map_exceptions(COMMON_EXCEPTIONS)
    def get(self, request, application_id: int):
        contents = ContentsHandler().get_application_contents(
            request.user, application_id, exclude_data=_exclude_data_requested(request)
        )
        return _streaming_json_response(contents)
