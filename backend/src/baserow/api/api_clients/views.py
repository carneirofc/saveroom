from django.db import transaction

from drf_spectacular.openapi import OpenApiParameter, OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.status import HTTP_200_OK, HTTP_204_NO_CONTENT
from rest_framework.views import APIView

from baserow.api.decorators import map_exceptions, validate_body
from baserow.api.errors import ERROR_GROUP_DOES_NOT_EXIST, ERROR_USER_NOT_IN_GROUP
from baserow.api.schemas import get_error_schema
from baserow.core.api_clients.exceptions import (
    ApiClientDoesNotBelongToUser,
    ApiClientDoesNotExist,
    ApiClientKeyDoesNotExist,
    InvalidApiClientScope,
)
from baserow.core.api_clients.handler import ApiClientHandler
from baserow.core.exceptions import UserNotInWorkspace, WorkspaceDoesNotExist
from baserow.core.handler import CoreHandler

from .errors import (
    ERROR_API_CLIENT_DOES_NOT_BELONG_TO_USER,
    ERROR_API_CLIENT_DOES_NOT_EXIST,
    ERROR_API_CLIENT_KEY_DOES_NOT_EXIST,
    ERROR_INVALID_API_CLIENT_SCOPE,
)
from .serializers import (
    ApiClientKeySerializer,
    ApiClientSerializer,
    CreateApiClientKeySerializer,
    CreateApiClientSerializer,
    CreatedApiClientKeySerializer,
    UpdateApiClientSerializer,
)

COMMON_EXCEPTIONS = {
    WorkspaceDoesNotExist: ERROR_GROUP_DOES_NOT_EXIST,
    UserNotInWorkspace: ERROR_USER_NOT_IN_GROUP,
    ApiClientDoesNotExist: ERROR_API_CLIENT_DOES_NOT_EXIST,
    ApiClientKeyDoesNotExist: ERROR_API_CLIENT_KEY_DOES_NOT_EXIST,
    ApiClientDoesNotBelongToUser: ERROR_API_CLIENT_DOES_NOT_BELONG_TO_USER,
    InvalidApiClientScope: ERROR_INVALID_API_CLIENT_SCOPE,
}


class ApiClientsView(APIView):
    permission_classes = (IsAuthenticated,)

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="workspace_id",
                location=OpenApiParameter.PATH,
                type=OpenApiTypes.INT,
                description="The workspace to list the API clients of.",
                required=True,
            )
        ],
        tags=["API clients"],
        operation_id="list_api_clients",
        description=(
            "Lists the API clients the authenticated user owns in the given workspace. "
            "An API client is a non human integration that acts on behalf of the user "
            "that created it, limited to the workspace and the scopes it was granted."
        ),
        responses={
            200: ApiClientSerializer(many=True),
            400: get_error_schema(["ERROR_USER_NOT_IN_GROUP"]),
            404: get_error_schema(["ERROR_GROUP_DOES_NOT_EXIST"]),
        },
    )
    @map_exceptions(COMMON_EXCEPTIONS)
    def get(self, request, workspace_id: int):
        clients = ApiClientHandler().list_clients(request.user, workspace_id)
        return Response(ApiClientSerializer(clients, many=True).data)

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="workspace_id",
                location=OpenApiParameter.PATH,
                type=OpenApiTypes.INT,
                description="The workspace to create the API client in.",
                required=True,
            )
        ],
        tags=["API clients"],
        operation_id="create_api_client",
        description=(
            "Creates a new API client in the given workspace. The client has no keys "
            "yet, issue one with the create key endpoint."
        ),
        request=CreateApiClientSerializer,
        responses={
            200: ApiClientSerializer,
            400: get_error_schema(
                [
                    "ERROR_USER_NOT_IN_GROUP",
                    "ERROR_REQUEST_BODY_VALIDATION",
                    "ERROR_INVALID_API_CLIENT_SCOPE",
                ]
            ),
            404: get_error_schema(["ERROR_GROUP_DOES_NOT_EXIST"]),
        },
    )
    @map_exceptions(COMMON_EXCEPTIONS)
    @validate_body(CreateApiClientSerializer, return_validated=True)
    @transaction.atomic
    def post(self, request, data, workspace_id: int):
        workspace = CoreHandler().get_workspace(workspace_id)
        client = ApiClientHandler().create_client(
            request.user, workspace, data["name"], data["scopes"]
        )
        return Response(ApiClientSerializer(client).data)


class ApiClientView(APIView):
    permission_classes = (IsAuthenticated,)

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="client_id",
                location=OpenApiParameter.PATH,
                type=OpenApiTypes.INT,
                description="The API client to return.",
                required=True,
            )
        ],
        tags=["API clients"],
        operation_id="get_api_client",
        description="Returns a single API client of the authenticated user.",
        responses={
            200: ApiClientSerializer,
            400: get_error_schema(["ERROR_USER_NOT_IN_GROUP"]),
            404: get_error_schema(["ERROR_API_CLIENT_DOES_NOT_EXIST"]),
        },
    )
    @map_exceptions(COMMON_EXCEPTIONS)
    def get(self, request, client_id: int):
        client = ApiClientHandler().get_client(request.user, client_id)
        return Response(ApiClientSerializer(client).data)

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="client_id",
                location=OpenApiParameter.PATH,
                type=OpenApiTypes.INT,
                description="The API client to update.",
                required=True,
            )
        ],
        tags=["API clients"],
        operation_id="update_api_client",
        description=(
            "Updates the name, scopes or active state of an API client. Setting "
            "`is_active` to false immediately stops every key of the client from "
            "working, without deleting anything."
        ),
        request=UpdateApiClientSerializer,
        responses={
            200: ApiClientSerializer,
            400: get_error_schema(
                [
                    "ERROR_USER_NOT_IN_GROUP",
                    "ERROR_REQUEST_BODY_VALIDATION",
                    "ERROR_INVALID_API_CLIENT_SCOPE",
                ]
            ),
            401: get_error_schema(["ERROR_API_CLIENT_DOES_NOT_BELONG_TO_USER"]),
            404: get_error_schema(["ERROR_API_CLIENT_DOES_NOT_EXIST"]),
        },
    )
    @map_exceptions(COMMON_EXCEPTIONS)
    @validate_body(UpdateApiClientSerializer, return_validated=True)
    @transaction.atomic
    def patch(self, request, data, client_id: int):
        handler = ApiClientHandler()
        client = handler.get_client(request.user, client_id)
        client = handler.update_client(request.user, client, **data)
        return Response(ApiClientSerializer(client).data)

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="client_id",
                location=OpenApiParameter.PATH,
                type=OpenApiTypes.INT,
                description="The API client to delete.",
                required=True,
            )
        ],
        tags=["API clients"],
        operation_id="delete_api_client",
        description="Deletes an API client and every key that belongs to it.",
        responses={
            204: None,
            400: get_error_schema(["ERROR_USER_NOT_IN_GROUP"]),
            401: get_error_schema(["ERROR_API_CLIENT_DOES_NOT_BELONG_TO_USER"]),
            404: get_error_schema(["ERROR_API_CLIENT_DOES_NOT_EXIST"]),
        },
    )
    @map_exceptions(COMMON_EXCEPTIONS)
    @transaction.atomic
    def delete(self, request, client_id: int):
        handler = ApiClientHandler()
        client = handler.get_client(request.user, client_id)
        handler.delete_client(request.user, client)
        return Response(status=HTTP_204_NO_CONTENT)


class ApiClientKeysView(APIView):
    permission_classes = (IsAuthenticated,)

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="client_id",
                location=OpenApiParameter.PATH,
                type=OpenApiTypes.INT,
                description="The API client to issue a key for.",
                required=True,
            )
        ],
        tags=["API clients"],
        operation_id="create_api_client_key",
        description=(
            "Issues a new key for an API client. The response contains the full key in "
            "the `key` field. Only a hash of it is stored, so this is the only moment "
            "it can be read. Use it as the `Authorization: Client <key>` header."
        ),
        request=CreateApiClientKeySerializer,
        responses={
            200: CreatedApiClientKeySerializer,
            400: get_error_schema(
                ["ERROR_USER_NOT_IN_GROUP", "ERROR_REQUEST_BODY_VALIDATION"]
            ),
            401: get_error_schema(["ERROR_API_CLIENT_DOES_NOT_BELONG_TO_USER"]),
            404: get_error_schema(["ERROR_API_CLIENT_DOES_NOT_EXIST"]),
        },
    )
    @map_exceptions(COMMON_EXCEPTIONS)
    @validate_body(CreateApiClientKeySerializer, return_validated=True)
    @transaction.atomic
    def post(self, request, data, client_id: int):
        handler = ApiClientHandler()
        client = handler.get_client(request.user, client_id)
        key, raw_key = handler.create_key(
            request.user,
            client,
            name=data.get("name", ""),
            expires_on=data.get("expires_on"),
        )

        response = CreatedApiClientKeySerializer(key).data
        response["key"] = raw_key
        return Response(response, status=HTTP_200_OK)


class ApiClientKeyView(APIView):
    permission_classes = (IsAuthenticated,)

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="key_id",
                location=OpenApiParameter.PATH,
                type=OpenApiTypes.INT,
                description="The API client key to revoke.",
                required=True,
            )
        ],
        tags=["API clients"],
        operation_id="revoke_api_client_key",
        description=(
            "Revokes an API client key. The key stops working immediately, but the "
            "record is kept so the revocation stays visible."
        ),
        responses={
            200: ApiClientKeySerializer,
            400: get_error_schema(["ERROR_USER_NOT_IN_GROUP"]),
            401: get_error_schema(["ERROR_API_CLIENT_DOES_NOT_BELONG_TO_USER"]),
            404: get_error_schema(["ERROR_API_CLIENT_KEY_DOES_NOT_EXIST"]),
        },
    )
    @map_exceptions(COMMON_EXCEPTIONS)
    @transaction.atomic
    def delete(self, request, key_id: int):
        handler = ApiClientHandler()
        key = handler.get_key(request.user, key_id)
        key = handler.revoke_key(request.user, key)
        return Response(ApiClientKeySerializer(key).data)
