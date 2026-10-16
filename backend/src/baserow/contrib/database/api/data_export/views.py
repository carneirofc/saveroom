from django.db import transaction

from drf_spectacular.openapi import OpenApiParameter, OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from baserow.api.api_clients.authentication import (
    ApiClientAuthentication,
    HasApiClientScope,
)
from baserow.api.applications.errors import ERROR_APPLICATION_DOES_NOT_EXIST
from baserow.api.data_destinations.errors import (
    ERROR_DATA_DESTINATION_DOES_NOT_EXIST,
    ERROR_DATA_DESTINATION_PURPOSE_NOT_ALLOWED,
)
from baserow.api.decorators import map_exceptions, validate_body
from baserow.api.errors import (
    ERROR_GROUP_DOES_NOT_EXIST,
    ERROR_PERMISSION_DENIED,
    ERROR_USER_NOT_IN_GROUP,
)
from baserow.api.schemas import get_error_schema
from baserow.contrib.database.data_export.exceptions import (
    InvalidTableExportScheduleCron,
    TableExportScheduleDoesNotExist,
    TableExportTablesNotInDatabase,
)
from baserow.contrib.database.data_export.models import TableExportSchedule
from baserow.contrib.database.data_export.schedule_handler import (
    TableExportScheduleHandler,
)
from baserow.contrib.database.models import Database
from baserow.core.data_destinations.exceptions import (
    DataDestinationDoesNotExist,
    DataDestinationPurposeNotAllowed,
)
from baserow.core.exceptions import (
    ApplicationDoesNotExist,
    PermissionDenied,
    UserNotInWorkspace,
    WorkspaceDoesNotExist,
)
from baserow.core.handler import CoreHandler

from .errors import (
    ERROR_INVALID_TABLE_EXPORT_SCHEDULE_CRON,
    ERROR_TABLE_EXPORT_SCHEDULE_DOES_NOT_EXIST,
    ERROR_TABLE_EXPORT_TABLES_NOT_IN_DATABASE,
)
from .serializers import (
    CreateTableExportScheduleSerializer,
    RunQueuedSerializer,
    RunTableExportScheduleSerializer,
    TableExportRunSerializer,
    TableExportScheduleSerializer,
    UpdateTableExportScheduleSerializer,
)

COMMON_EXCEPTIONS = {
    WorkspaceDoesNotExist: ERROR_GROUP_DOES_NOT_EXIST,
    UserNotInWorkspace: ERROR_USER_NOT_IN_GROUP,
    PermissionDenied: ERROR_PERMISSION_DENIED,
    ApplicationDoesNotExist: ERROR_APPLICATION_DOES_NOT_EXIST,
    TableExportScheduleDoesNotExist: ERROR_TABLE_EXPORT_SCHEDULE_DOES_NOT_EXIST,
    InvalidTableExportScheduleCron: ERROR_INVALID_TABLE_EXPORT_SCHEDULE_CRON,
    TableExportTablesNotInDatabase: ERROR_TABLE_EXPORT_TABLES_NOT_IN_DATABASE,
    DataDestinationDoesNotExist: ERROR_DATA_DESTINATION_DOES_NOT_EXIST,
    DataDestinationPurposeNotAllowed: ERROR_DATA_DESTINATION_PURPOSE_NOT_ALLOWED,
}

# The last runs returned by the runs endpoint.
RUNS_LIMIT = 100

WORKSPACE_ID_PARAMETER = OpenApiParameter(
    name="workspace_id",
    location=OpenApiParameter.PATH,
    type=OpenApiTypes.INT,
    description="The id of the workspace.",
    required=True,
)
SCHEDULE_ID_PARAMETER = OpenApiParameter(
    name="schedule_id",
    location=OpenApiParameter.PATH,
    type=OpenApiTypes.INT,
    description="The id of the table export schedule.",
    required=True,
)
TAGS = ["Database table export schedules"]


class TableExportScheduleWorkspaceMixin:
    """
    Binds an API client to the workspace of the schedule in the url.
    """

    def get_api_client_workspace_id(self, request, schedule_id=None, **kwargs):
        return (
            TableExportSchedule.objects.filter(id=schedule_id)
            .values_list("workspace_id", flat=True)
            .first()
        )


class TableExportSchedulesView(APIView):
    authentication_classes = APIView.authentication_classes + [ApiClientAuthentication]
    permission_classes = (IsAuthenticated, HasApiClientScope)
    api_client_scopes = {"GET": "schedule.read", "POST": "schedule.write"}

    @extend_schema(
        parameters=[WORKSPACE_ID_PARAMETER],
        tags=TAGS,
        operation_id="list_table_export_schedules",
        description="Lists the datalake table export schedules of a workspace.",
        responses={
            200: TableExportScheduleSerializer(many=True),
            400: get_error_schema(["ERROR_USER_NOT_IN_GROUP"]),
            404: get_error_schema(["ERROR_GROUP_DOES_NOT_EXIST"]),
        },
    )
    @map_exceptions(COMMON_EXCEPTIONS)
    def get(self, request, workspace_id: int):
        schedules = TableExportScheduleHandler().list_schedules(
            request.user, workspace_id
        )
        return Response(TableExportScheduleSerializer(schedules, many=True).data)

    @extend_schema(
        parameters=[WORKSPACE_ID_PARAMETER],
        tags=TAGS,
        operation_id="create_table_export_schedule",
        description=(
            "Creates a recurring Parquet export of the tables of a database to a "
            "datalake destination. The exports run on behalf of the user creating "
            "the schedule, who must be allowed to export every table. The first "
            "export of a table is full, later ones are incremental whenever they can "
            "be merged correctly."
        ),
        request=CreateTableExportScheduleSerializer,
        responses={
            200: TableExportScheduleSerializer,
            400: get_error_schema(
                [
                    "ERROR_USER_NOT_IN_GROUP",
                    "ERROR_REQUEST_BODY_VALIDATION",
                    "ERROR_PERMISSION_DENIED",
                    "ERROR_INVALID_TABLE_EXPORT_SCHEDULE_CRON",
                    "ERROR_TABLE_EXPORT_TABLES_NOT_IN_DATABASE",
                    "ERROR_DATA_DESTINATION_PURPOSE_NOT_ALLOWED",
                ]
            ),
            404: get_error_schema(
                [
                    "ERROR_GROUP_DOES_NOT_EXIST",
                    "ERROR_APPLICATION_DOES_NOT_EXIST",
                    "ERROR_DATA_DESTINATION_DOES_NOT_EXIST",
                ]
            ),
        },
    )
    @map_exceptions(COMMON_EXCEPTIONS)
    @validate_body(CreateTableExportScheduleSerializer, return_validated=True)
    @transaction.atomic
    def post(self, request, data, workspace_id: int):
        workspace = CoreHandler().get_workspace(workspace_id)
        database = (
            Database.objects.filter(id=data["database_id"], workspace=workspace)
            .select_related("workspace")
            .first()
        )
        if database is None:
            raise ApplicationDoesNotExist(
                f"The database {data['database_id']} does not exist in the workspace."
            )

        schedule = TableExportScheduleHandler().create_schedule(
            request.user,
            database,
            name=data["name"],
            cron=data["cron"],
            destination=data["destination"],
            tz_name=data["timezone"],
            table_ids=data["table_ids"],
            full_every_n=data["full_every_n"],
            column_naming=data["column_naming"],
            is_active=data["is_active"],
        )
        return Response(TableExportScheduleSerializer(schedule).data)


class TableExportScheduleView(TableExportScheduleWorkspaceMixin, APIView):
    authentication_classes = APIView.authentication_classes + [ApiClientAuthentication]
    permission_classes = (IsAuthenticated, HasApiClientScope)
    api_client_scopes = {
        "GET": "schedule.read",
        "PATCH": "schedule.write",
        "DELETE": "schedule.write",
    }

    @extend_schema(
        parameters=[SCHEDULE_ID_PARAMETER],
        tags=TAGS,
        operation_id="get_table_export_schedule",
        description="Returns a single table export schedule.",
        responses={
            200: TableExportScheduleSerializer,
            400: get_error_schema(["ERROR_USER_NOT_IN_GROUP"]),
            404: get_error_schema(["ERROR_TABLE_EXPORT_SCHEDULE_DOES_NOT_EXIST"]),
        },
    )
    @map_exceptions(COMMON_EXCEPTIONS)
    def get(self, request, schedule_id: int):
        schedule = TableExportScheduleHandler().get_schedule(request.user, schedule_id)
        return Response(TableExportScheduleSerializer(schedule).data)

    @extend_schema(
        parameters=[SCHEDULE_ID_PARAMETER],
        tags=TAGS,
        operation_id="update_table_export_schedule",
        description=(
            "Updates a table export schedule. The exports then run on behalf of the "
            "updating user. Changing the tables or the column naming forgets the "
            "watermarks, so the next export of every table is full."
        ),
        request=UpdateTableExportScheduleSerializer,
        responses={
            200: TableExportScheduleSerializer,
            400: get_error_schema(
                [
                    "ERROR_USER_NOT_IN_GROUP",
                    "ERROR_REQUEST_BODY_VALIDATION",
                    "ERROR_PERMISSION_DENIED",
                    "ERROR_INVALID_TABLE_EXPORT_SCHEDULE_CRON",
                    "ERROR_TABLE_EXPORT_TABLES_NOT_IN_DATABASE",
                    "ERROR_DATA_DESTINATION_PURPOSE_NOT_ALLOWED",
                ]
            ),
            404: get_error_schema(
                [
                    "ERROR_TABLE_EXPORT_SCHEDULE_DOES_NOT_EXIST",
                    "ERROR_DATA_DESTINATION_DOES_NOT_EXIST",
                ]
            ),
        },
    )
    @map_exceptions(COMMON_EXCEPTIONS)
    @validate_body(UpdateTableExportScheduleSerializer, return_validated=True)
    @transaction.atomic
    def patch(self, request, data, schedule_id: int):
        handler = TableExportScheduleHandler()
        schedule = handler.get_schedule(request.user, schedule_id, for_update=True)
        schedule = handler.update_schedule(request.user, schedule, **data)
        return Response(TableExportScheduleSerializer(schedule).data)

    @extend_schema(
        parameters=[SCHEDULE_ID_PARAMETER],
        tags=TAGS,
        operation_id="delete_table_export_schedule",
        description=(
            "Deletes a table export schedule. Files already written to the "
            "destination are kept."
        ),
        responses={
            204: None,
            400: get_error_schema(["ERROR_USER_NOT_IN_GROUP"]),
            404: get_error_schema(["ERROR_TABLE_EXPORT_SCHEDULE_DOES_NOT_EXIST"]),
        },
    )
    @map_exceptions(COMMON_EXCEPTIONS)
    @transaction.atomic
    def delete(self, request, schedule_id: int):
        handler = TableExportScheduleHandler()
        schedule = handler.get_schedule(request.user, schedule_id)
        handler.delete_schedule(request.user, schedule)
        return Response(status=status.HTTP_204_NO_CONTENT)


class RunTableExportScheduleView(TableExportScheduleWorkspaceMixin, APIView):
    authentication_classes = APIView.authentication_classes + [ApiClientAuthentication]
    permission_classes = (IsAuthenticated, HasApiClientScope)
    api_client_scopes = {"POST": "schedule.write"}

    @extend_schema(
        parameters=[SCHEDULE_ID_PARAMETER],
        tags=TAGS,
        operation_id="run_table_export_schedule",
        description=(
            "Queues an export of every table of the schedule right now, without "
            "changing when it next runs. Follow the progress through the runs "
            "endpoint."
        ),
        request=RunTableExportScheduleSerializer,
        responses={
            202: RunQueuedSerializer,
            400: get_error_schema(
                ["ERROR_USER_NOT_IN_GROUP", "ERROR_REQUEST_BODY_VALIDATION"]
            ),
            404: get_error_schema(["ERROR_TABLE_EXPORT_SCHEDULE_DOES_NOT_EXIST"]),
        },
    )
    @map_exceptions(COMMON_EXCEPTIONS)
    @validate_body(RunTableExportScheduleSerializer, return_validated=True)
    @transaction.atomic
    def post(self, request, data, schedule_id: int):
        handler = TableExportScheduleHandler()
        schedule = handler.get_schedule(request.user, schedule_id)
        handler.run_schedule(request.user, schedule, mode=data["mode"])
        return Response(
            {"schedule_id": schedule.id, "mode": data["mode"]},
            status=status.HTTP_202_ACCEPTED,
        )


class TableExportRunsView(TableExportScheduleWorkspaceMixin, APIView):
    authentication_classes = APIView.authentication_classes + [ApiClientAuthentication]
    permission_classes = (IsAuthenticated, HasApiClientScope)
    api_client_scopes = {"GET": "schedule.read"}

    @extend_schema(
        parameters=[SCHEDULE_ID_PARAMETER],
        tags=TAGS,
        operation_id="list_table_export_runs",
        description=(
            f"Lists the last {RUNS_LIMIT} exports of a schedule, one entry per table "
            "per run, most recent first."
        ),
        responses={
            200: TableExportRunSerializer(many=True),
            400: get_error_schema(["ERROR_USER_NOT_IN_GROUP"]),
            404: get_error_schema(["ERROR_TABLE_EXPORT_SCHEDULE_DOES_NOT_EXIST"]),
        },
    )
    @map_exceptions(COMMON_EXCEPTIONS)
    def get(self, request, schedule_id: int):
        handler = TableExportScheduleHandler()
        schedule = handler.get_schedule(request.user, schedule_id)
        runs = handler.list_runs(request.user, schedule)[:RUNS_LIMIT]
        return Response(TableExportRunSerializer(runs, many=True).data)


class ResetTableExportStateView(TableExportScheduleWorkspaceMixin, APIView):
    authentication_classes = APIView.authentication_classes + [ApiClientAuthentication]
    permission_classes = (IsAuthenticated, HasApiClientScope)
    api_client_scopes = {"POST": "schedule.write"}

    @extend_schema(
        parameters=[SCHEDULE_ID_PARAMETER],
        tags=TAGS,
        operation_id="reset_table_export_state",
        description=(
            "Forgets the incremental watermarks of the schedule, so the next export "
            "of every table is full. Use it after restoring or rebuilding the lake."
        ),
        request=None,
        responses={
            204: None,
            400: get_error_schema(["ERROR_USER_NOT_IN_GROUP"]),
            404: get_error_schema(["ERROR_TABLE_EXPORT_SCHEDULE_DOES_NOT_EXIST"]),
        },
    )
    @map_exceptions(COMMON_EXCEPTIONS)
    @transaction.atomic
    def post(self, request, schedule_id: int):
        handler = TableExportScheduleHandler()
        schedule = handler.get_schedule(request.user, schedule_id)
        handler.reset_state(request.user, schedule)
        return Response(status=status.HTTP_204_NO_CONTENT)
