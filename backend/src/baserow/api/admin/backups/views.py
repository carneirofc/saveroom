from django.db import transaction

from drf_spectacular.openapi import OpenApiParameter, OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from rest_framework.status import HTTP_204_NO_CONTENT
from rest_framework.views import APIView

from baserow.api.backups.errors import (
    ERROR_BACKUP_SCHEDULE_DOES_NOT_EXIST,
    ERROR_INVALID_BACKUP_SCHEDULE_CRON,
    ERROR_REMOTE_BACKUP_CORRUPTED,
    ERROR_REMOTE_BACKUP_DOES_NOT_EXIST,
    ERROR_REMOTE_BACKUP_TRUST_NOT_ALLOWED,
)
from baserow.api.backups.views import COMMON_EXCEPTIONS, BackupDownloadView
from baserow.api.decorators import map_exceptions, validate_body
from baserow.api.download.handler import DOWNLOAD_EXCEPTIONS
from baserow.api.jobs.errors import ERROR_MAX_JOB_COUNT_EXCEEDED
from baserow.api.jobs.serializers import JobSerializer
from baserow.api.schemas import get_error_schema
from baserow.core.backups.destination import BackupDestinationHandler
from baserow.core.backups.exceptions import (
    BackupScheduleDoesNotExist,
    InvalidBackupScheduleCron,
    RemoteBackupCorrupted,
    RemoteBackupDoesNotExist,
    RemoteBackupTrustNotAllowed,
)
from baserow.core.backups.handler import BackupHandler
from baserow.core.backups.schedule_handler import BackupScheduleHandler
from baserow.core.handler import CoreHandler
from baserow.core.jobs.exceptions import MaxJobCountExceeded
from baserow.core.jobs.registries import job_type_registry

from .serializers import (
    BackupScheduleSerializer,
    BackupSerializer,
    CreateBackupScheduleSerializer,
    CreateBackupSerializer,
    ListBackupsSerializer,
    ListRemoteBackupsSerializer,
    RestoreBackupSerializer,
    RestoreRemoteBackupSerializer,
    UpdateBackupScheduleSerializer,
)

ADMIN_EXCEPTIONS = {
    **COMMON_EXCEPTIONS,
    MaxJobCountExceeded: ERROR_MAX_JOB_COUNT_EXCEEDED,
}

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
    description="The id of the backup schedule.",
    required=True,
)

DESTINATION_PARAMETER = OpenApiParameter(
    name="destination",
    location=OpenApiParameter.PATH,
    type=OpenApiTypes.STR,
    description="The name of the data destination.",
    required=True,
)


class BackupsAdminView(APIView):
    """
    Staff-only, workspace-membership-agnostic counterpart of
    `baserow.api.backups.views.BackupsView`. Calls the same `BackupHandler` methods,
    which succeed for staff on any workspace thanks to
    `StaffBypassPermissionManagerType`.
    """

    permission_classes = (IsAdminUser,)

    @extend_schema(
        parameters=[WORKSPACE_ID_PARAMETER],
        tags=["Admin"],
        operation_id="admin_list_backups",
        description=(
            "Lists the finished backups of a workspace that were created by the "
            "requesting staff user, most recent first. Staff can do this for any "
            "workspace, regardless of membership."
        ),
        responses={
            200: ListBackupsSerializer,
            404: get_error_schema(["ERROR_GROUP_DOES_NOT_EXIST"]),
        },
    )
    @map_exceptions(COMMON_EXCEPTIONS)
    def get(self, request, workspace_id: int):
        backups = BackupHandler().list_backups(request.user, workspace_id)
        return Response(ListBackupsSerializer({"results": backups}).data)


class StartBackupAdminView(APIView):
    permission_classes = (IsAdminUser,)

    @extend_schema(
        parameters=[WORKSPACE_ID_PARAMETER],
        tags=["Admin"],
        operation_id="admin_start_backup",
        description="Starts a backup of a workspace as staff, for any workspace.",
        request=CreateBackupSerializer,
        responses={
            202: JobSerializer,
            400: get_error_schema(
                ["ERROR_REQUEST_BODY_VALIDATION", "ERROR_MAX_JOB_COUNT_EXCEEDED"]
            ),
            404: get_error_schema(["ERROR_GROUP_DOES_NOT_EXIST"]),
        },
    )
    @map_exceptions(ADMIN_EXCEPTIONS)
    @validate_body(CreateBackupSerializer, return_validated=True)
    @transaction.atomic
    def post(self, request, data, workspace_id: int):
        job = BackupHandler().start_backup(
            request.user,
            workspace_id,
            application_ids=data.get("application_ids"),
            only_structure=data.get("only_structure", False),
            destination=data.get("destination") or None,
        )
        serializer = job_type_registry.get_serializer(job, JobSerializer)
        return Response(serializer.data, status=status.HTTP_202_ACCEPTED)


class BackupAdminView(APIView):
    permission_classes = (IsAdminUser,)

    @extend_schema(
        parameters=[
            WORKSPACE_ID_PARAMETER,
            OpenApiParameter(
                name="resource_id",
                location=OpenApiParameter.PATH,
                type=OpenApiTypes.INT,
                description="The id of the backup resource.",
                required=True,
            ),
        ],
        tags=["Admin"],
        operation_id="admin_get_backup",
        description="Returns a single backup, including its download URL.",
        responses={
            200: ListBackupsSerializer,
            404: get_error_schema(
                ["ERROR_GROUP_DOES_NOT_EXIST", "ERROR_RESOURCE_DOES_NOT_EXIST"]
            ),
        },
    )
    @map_exceptions(COMMON_EXCEPTIONS)
    def get(self, request, workspace_id: int, resource_id: int):
        backup = BackupHandler().get_backup(request.user, workspace_id, resource_id)
        # The list endpoint answers with `BackupSerializer`, so the item endpoint uses
        # it too: otherwise it would omit the resource id, destination and download
        # url its own description promises.
        return Response(BackupSerializer(backup).data)

    @extend_schema(
        parameters=[
            WORKSPACE_ID_PARAMETER,
            OpenApiParameter(
                name="resource_id",
                location=OpenApiParameter.PATH,
                type=OpenApiTypes.INT,
                description="The id of the backup resource to delete.",
                required=True,
            ),
        ],
        tags=["Admin"],
        operation_id="admin_delete_backup",
        description="Marks the archive of a backup for deletion.",
        responses={
            204: None,
            404: get_error_schema(
                ["ERROR_GROUP_DOES_NOT_EXIST", "ERROR_RESOURCE_DOES_NOT_EXIST"]
            ),
        },
    )
    @map_exceptions(COMMON_EXCEPTIONS)
    @transaction.atomic
    def delete(self, request, workspace_id: int, resource_id: int):
        handler = BackupHandler()
        handler.get_backup(request.user, workspace_id, resource_id)
        handler.delete_backup(request.user, resource_id)
        return Response(status=HTTP_204_NO_CONTENT)


class RestoreBackupAdminView(APIView):
    permission_classes = (IsAdminUser,)

    @extend_schema(
        parameters=[WORKSPACE_ID_PARAMETER],
        tags=["Admin"],
        operation_id="admin_restore_backup",
        description="Restores a backup into a workspace, as staff.",
        request=RestoreBackupSerializer,
        responses={
            202: JobSerializer,
            400: get_error_schema(
                [
                    "ERROR_REQUEST_BODY_VALIDATION",
                    "ERROR_RESOURCE_IS_INVALID",
                    "ERROR_APPLICATION_IDS_NOT_FOUND",
                    "ERROR_MAX_JOB_COUNT_EXCEEDED",
                ]
            ),
            404: get_error_schema(
                ["ERROR_GROUP_DOES_NOT_EXIST", "ERROR_RESOURCE_DOES_NOT_EXIST"]
            ),
        },
    )
    @map_exceptions(ADMIN_EXCEPTIONS)
    @validate_body(RestoreBackupSerializer, return_validated=True)
    @transaction.atomic
    def post(self, request, data, workspace_id: int):
        job = BackupHandler().start_restore(
            request.user,
            workspace_id,
            data["resource_id"],
            application_ids=data.get("application_ids"),
        )
        serializer = job_type_registry.get_serializer(job, JobSerializer)
        return Response(serializer.data, status=status.HTTP_202_ACCEPTED)


class BackupSchedulesAdminView(APIView):
    permission_classes = (IsAdminUser,)

    @extend_schema(
        parameters=[WORKSPACE_ID_PARAMETER],
        tags=["Admin"],
        operation_id="admin_list_backup_schedules",
        description="Lists the backup schedules of a workspace, as staff.",
        responses={
            200: BackupScheduleSerializer(many=True),
            404: get_error_schema(["ERROR_GROUP_DOES_NOT_EXIST"]),
        },
    )
    @map_exceptions(COMMON_EXCEPTIONS)
    def get(self, request, workspace_id: int):
        schedules = BackupScheduleHandler().list_schedules(request.user, workspace_id)
        return Response(BackupScheduleSerializer(schedules, many=True).data)

    @extend_schema(
        parameters=[WORKSPACE_ID_PARAMETER],
        tags=["Admin"],
        operation_id="admin_create_backup_schedule",
        description="Creates a recurring backup of a workspace, as staff.",
        request=CreateBackupScheduleSerializer,
        responses={
            200: BackupScheduleSerializer,
            400: get_error_schema(
                ["ERROR_REQUEST_BODY_VALIDATION", "ERROR_INVALID_BACKUP_SCHEDULE_CRON"]
            ),
            404: get_error_schema(["ERROR_GROUP_DOES_NOT_EXIST"]),
        },
    )
    @map_exceptions(
        {
            **COMMON_EXCEPTIONS,
            BackupScheduleDoesNotExist: ERROR_BACKUP_SCHEDULE_DOES_NOT_EXIST,
            InvalidBackupScheduleCron: ERROR_INVALID_BACKUP_SCHEDULE_CRON,
        }
    )
    @validate_body(CreateBackupScheduleSerializer, return_validated=True)
    @transaction.atomic
    def post(self, request, data, workspace_id: int):
        workspace = CoreHandler().get_workspace(workspace_id)
        schedule = BackupScheduleHandler().create_schedule(
            request.user,
            workspace,
            name=data["name"],
            cron=data["cron"],
            tz_name=data["timezone"],
            application_ids=data["application_ids"],
            only_structure=data["only_structure"],
            destination=data["destination"],
            keep_last=data["keep_last"],
            keep_days=data["keep_days"],
            is_active=data["is_active"],
        )
        return Response(BackupScheduleSerializer(schedule).data)


class BackupScheduleAdminView(APIView):
    permission_classes = (IsAdminUser,)

    @extend_schema(
        parameters=[SCHEDULE_ID_PARAMETER],
        tags=["Admin"],
        operation_id="admin_get_backup_schedule",
        description="Returns a single backup schedule.",
        responses={
            200: BackupScheduleSerializer,
            404: get_error_schema(["ERROR_BACKUP_SCHEDULE_DOES_NOT_EXIST"]),
        },
    )
    @map_exceptions(
        {
            **COMMON_EXCEPTIONS,
            BackupScheduleDoesNotExist: ERROR_BACKUP_SCHEDULE_DOES_NOT_EXIST,
        }
    )
    def get(self, request, schedule_id: int):
        schedule = BackupScheduleHandler().get_schedule(request.user, schedule_id)
        return Response(BackupScheduleSerializer(schedule).data)

    @extend_schema(
        parameters=[SCHEDULE_ID_PARAMETER],
        tags=["Admin"],
        operation_id="admin_update_backup_schedule",
        description="Updates a backup schedule.",
        request=UpdateBackupScheduleSerializer,
        responses={
            200: BackupScheduleSerializer,
            400: get_error_schema(
                ["ERROR_REQUEST_BODY_VALIDATION", "ERROR_INVALID_BACKUP_SCHEDULE_CRON"]
            ),
            404: get_error_schema(["ERROR_BACKUP_SCHEDULE_DOES_NOT_EXIST"]),
        },
    )
    @map_exceptions(
        {
            **COMMON_EXCEPTIONS,
            BackupScheduleDoesNotExist: ERROR_BACKUP_SCHEDULE_DOES_NOT_EXIST,
            InvalidBackupScheduleCron: ERROR_INVALID_BACKUP_SCHEDULE_CRON,
        }
    )
    @validate_body(UpdateBackupScheduleSerializer, return_validated=True)
    @transaction.atomic
    def patch(self, request, data, schedule_id: int):
        handler = BackupScheduleHandler()
        schedule = handler.get_schedule(request.user, schedule_id, for_update=True)
        schedule = handler.update_schedule(request.user, schedule, **data)
        return Response(BackupScheduleSerializer(schedule).data)

    @extend_schema(
        parameters=[SCHEDULE_ID_PARAMETER],
        tags=["Admin"],
        operation_id="admin_delete_backup_schedule",
        description="Deletes a backup schedule. Backups it already made are kept.",
        responses={
            204: None,
            404: get_error_schema(["ERROR_BACKUP_SCHEDULE_DOES_NOT_EXIST"]),
        },
    )
    @map_exceptions(
        {
            **COMMON_EXCEPTIONS,
            BackupScheduleDoesNotExist: ERROR_BACKUP_SCHEDULE_DOES_NOT_EXIST,
        }
    )
    @transaction.atomic
    def delete(self, request, schedule_id: int):
        handler = BackupScheduleHandler()
        schedule = handler.get_schedule(request.user, schedule_id)
        handler.delete_schedule(request.user, schedule)
        return Response(status=HTTP_204_NO_CONTENT)


class RunBackupScheduleAdminView(APIView):
    permission_classes = (IsAdminUser,)

    @extend_schema(
        parameters=[SCHEDULE_ID_PARAMETER],
        tags=["Admin"],
        operation_id="admin_run_backup_schedule",
        description="Runs a backup schedule right now.",
        request=None,
        responses={
            202: JobSerializer,
            400: get_error_schema(["ERROR_MAX_JOB_COUNT_EXCEEDED"]),
            404: get_error_schema(["ERROR_BACKUP_SCHEDULE_DOES_NOT_EXIST"]),
        },
    )
    @map_exceptions(
        {
            **ADMIN_EXCEPTIONS,
            BackupScheduleDoesNotExist: ERROR_BACKUP_SCHEDULE_DOES_NOT_EXIST,
        }
    )
    @transaction.atomic
    def post(self, request, schedule_id: int):
        handler = BackupScheduleHandler()
        schedule = handler.get_schedule(request.user, schedule_id)
        job = handler.run_schedule(schedule, requested_by=request.user)
        serializer = job_type_registry.get_serializer(job, JobSerializer)
        return Response(serializer.data, status=status.HTTP_202_ACCEPTED)


class RemoteBackupsAdminView(APIView):
    permission_classes = (IsAdminUser,)

    @extend_schema(
        parameters=[DESTINATION_PARAMETER, WORKSPACE_ID_PARAMETER],
        tags=["Admin"],
        operation_id="admin_list_remote_backups",
        description="Lists the backups of a workspace on a data destination.",
        responses={
            200: ListRemoteBackupsSerializer,
            404: get_error_schema(
                ["ERROR_GROUP_DOES_NOT_EXIST", "ERROR_DATA_DESTINATION_DOES_NOT_EXIST"]
            ),
        },
    )
    @map_exceptions(COMMON_EXCEPTIONS)
    def get(self, request, destination: str, workspace_id: int):
        backups = BackupDestinationHandler().list_remote_backups(
            request.user, workspace_id, destination
        )
        return Response(ListRemoteBackupsSerializer({"results": backups}).data)


class RestoreRemoteBackupAdminView(APIView):
    permission_classes = (IsAdminUser,)

    @extend_schema(
        parameters=[DESTINATION_PARAMETER, WORKSPACE_ID_PARAMETER],
        tags=["Admin"],
        operation_id="admin_restore_remote_backup",
        description=(
            "Downloads a backup from a data destination and restores it into a "
            "workspace. Pass `trust_public_key` to trust a backup made by another "
            "instance, when the destination allows it."
        ),
        request=RestoreRemoteBackupSerializer,
        responses={
            202: JobSerializer,
            400: get_error_schema(
                [
                    "ERROR_REQUEST_BODY_VALIDATION",
                    "ERROR_INVALID_DATA_DESTINATION_KEY",
                    "ERROR_REMOTE_BACKUP_CORRUPTED",
                    "ERROR_UNTRUSTED_PUBLIC_KEY",
                    "ERROR_RESOURCE_IS_INVALID",
                    "ERROR_MAX_JOB_COUNT_EXCEEDED",
                ]
            ),
            403: get_error_schema(["ERROR_REMOTE_BACKUP_TRUST_NOT_ALLOWED"]),
            404: get_error_schema(
                [
                    "ERROR_GROUP_DOES_NOT_EXIST",
                    "ERROR_DATA_DESTINATION_DOES_NOT_EXIST",
                    "ERROR_REMOTE_BACKUP_DOES_NOT_EXIST",
                ]
            ),
        },
    )
    @map_exceptions(
        {
            **ADMIN_EXCEPTIONS,
            RemoteBackupDoesNotExist: ERROR_REMOTE_BACKUP_DOES_NOT_EXIST,
            RemoteBackupCorrupted: ERROR_REMOTE_BACKUP_CORRUPTED,
            RemoteBackupTrustNotAllowed: ERROR_REMOTE_BACKUP_TRUST_NOT_ALLOWED,
        }
    )
    @validate_body(RestoreRemoteBackupSerializer, return_validated=True)
    def post(self, request, data, destination: str, workspace_id: int):
        job = BackupDestinationHandler().restore_remote_backup(
            request.user,
            workspace_id,
            destination,
            data["key"],
            application_ids=data.get("application_ids"),
            trust_public_key=data["trust_public_key"],
        )
        serializer = job_type_registry.get_serializer(job, JobSerializer)
        return Response(serializer.data, status=status.HTTP_202_ACCEPTED)


class BackupDownloadAdminView(BackupDownloadView):
    """
    Staff counterpart of `baserow.api.backups.views.BackupDownloadView`. It resolves
    the backup the same way, which succeeds for staff on any workspace thanks to
    `StaffBypassPermissionManagerType`, and it is not reachable with an API client
    key: a machine credential uses the regular endpoint with its own scope.
    """

    authentication_classes = APIView.authentication_classes
    permission_classes = (IsAdminUser,)
    api_client_scopes = {}

    @extend_schema(
        parameters=[
            WORKSPACE_ID_PARAMETER,
            OpenApiParameter(
                name="resource_id",
                location=OpenApiParameter.PATH,
                type=OpenApiTypes.INT,
                description="The id of the backup resource to download.",
                required=True,
            ),
        ],
        tags=["Admin"],
        operation_id="admin_download_backup",
        description=(
            "Downloads the archive of a backup as staff, streamed from the server's "
            "file storage."
        ),
        request=None,
        responses={
            200: OpenApiTypes.BINARY,
            404: get_error_schema(
                ["ERROR_GROUP_DOES_NOT_EXIST", "ERROR_RESOURCE_DOES_NOT_EXIST"]
            ),
            410: get_error_schema(["ERROR_EXPORT_FILE_EXPIRED"]),
            500: get_error_schema(["ERROR_EXPORT_FILE_MISSING_FROM_STORAGE"]),
            503: get_error_schema(["ERROR_STORAGE_UNAVAILABLE"]),
        },
    )
    @map_exceptions({**ADMIN_EXCEPTIONS, **DOWNLOAD_EXCEPTIONS})
    def get(self, request, workspace_id: int, resource_id: int):
        return self.serve(request, workspace_id=workspace_id, resource_id=resource_id)

    @map_exceptions({**ADMIN_EXCEPTIONS, **DOWNLOAD_EXCEPTIONS})
    def head(self, request, workspace_id: int, resource_id: int):
        return self.serve(
            request,
            head_only=True,
            workspace_id=workspace_id,
            resource_id=resource_id,
        )
