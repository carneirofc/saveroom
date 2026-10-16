from typing import Any, Dict

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils.functional import lazy

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from baserow.api.decorators import map_exceptions
from baserow.api.download.authentication import DownloadTokenAuthentication
from baserow.api.download.handler import (
    DOWNLOAD_EXCEPTIONS,
    sanitize_download_name,
    serve_export_file,
)
from baserow.api.download.tokens import TABLE_EXPORT_DOWNLOAD
from baserow.api.errors import ERROR_USER_NOT_IN_GROUP
from baserow.api.schemas import get_error_schema
from baserow.api.utils import DiscriminatorMappingSerializer, validate_data
from baserow.contrib.database.api.export.errors import (
    ERROR_EXPORT_JOB_DOES_NOT_EXIST,
    ERROR_TABLE_ONLY_EXPORT_UNSUPPORTED,
)
from baserow.contrib.database.api.export.serializers import (
    BaseExporterOptionsSerializer,
    DisplayChoiceField,
    ExportJobSerializer,
)
from baserow.contrib.database.api.fields.errors import (
    ERROR_FILTER_FIELD_NOT_FOUND,
    ERROR_ORDER_BY_FIELD_NOT_FOUND,
    ERROR_ORDER_BY_FIELD_NOT_POSSIBLE,
)
from baserow.contrib.database.api.tables.errors import ERROR_TABLE_DOES_NOT_EXIST
from baserow.contrib.database.api.views.errors import (
    ERROR_VIEW_DOES_NOT_EXIST,
    ERROR_VIEW_FILTER_TYPE_DOES_NOT_EXIST,
    ERROR_VIEW_FILTER_TYPE_UNSUPPORTED_FIELD,
    ERROR_VIEW_GROUP_BY_FIELD_NOT_SUPPORTED,
    ERROR_VIEW_NOT_IN_TABLE,
)
from baserow.contrib.database.export.exceptions import (
    ExportJobDoesNotExistException,
    TableOnlyExportUnsupported,
)
from baserow.contrib.database.export.handler import ExportHandler
from baserow.contrib.database.export.models import ExportJob
from baserow.contrib.database.export.registries import table_exporter_registry
from baserow.contrib.database.fields.exceptions import (
    FilterFieldNotFound,
    OrderByFieldNotFound,
    OrderByFieldNotPossible,
)
from baserow.contrib.database.table.exceptions import TableDoesNotExist
from baserow.contrib.database.table.handler import TableHandler
from baserow.contrib.database.views.exceptions import (
    ViewDoesNotExist,
    ViewFilterTypeDoesNotExist,
    ViewFilterTypeNotAllowedForField,
    ViewGroupByFieldNotSupported,
    ViewNotInTable,
)
from baserow.contrib.database.views.handler import ViewHandler
from baserow.core.exceptions import UserNotInWorkspace

User = get_user_model()

# A placeholder serializer only used to generate correct api documentation.
CreateExportJobSerializer = DiscriminatorMappingSerializer(
    "Export",
    lazy(table_exporter_registry.get_option_serializer_map, dict)(),
    type_field_name="exporter_type",
)


def _validate_options(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Looks up the exporter_type from the data, selects the correct export
    options serializer based on the exporter_type and finally validates the data using
    that serializer.

    Uses ``return_validated=True`` so that omitted optional fields (e.g.
    ``group_by``) stay absent instead of appearing as ``None``.  Because
    ``validated_data`` bypasses ``to_representation()``, we manually apply the
    conversion for every ``DisplayChoiceField`` (delimiter, charset) so the
    downstream code receives the actual Python values, not the display names.

    :param data: A dict of data to serialize using an exporter options serializer.
    :return: validated export options data
    """

    option_serializers = table_exporter_registry.get_option_serializer_map()
    validated_exporter_type = validate_data(BaseExporterOptionsSerializer, data)
    serializer_class = option_serializers[validated_exporter_type["exporter_type"]]
    validated = validate_data(serializer_class, data, return_validated=True)

    for field_name, field in serializer_class().fields.items():
        if isinstance(field, DisplayChoiceField) and field_name in validated:
            validated[field_name] = field.to_representation(validated[field_name])

    return validated


class ExportTableView(APIView):
    permission_classes = (IsAuthenticated,)

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="table_id",
                location=OpenApiParameter.PATH,
                type=OpenApiTypes.INT,
                description="The table id to create and start an export job for",
            )
        ],
        tags=["Database table export"],
        operation_id="export_table",
        description=(
            "Creates and starts a new export job for a table given some exporter "
            "options. Returns an error if the requesting user does not have permissions"
            "to view the table."
        ),
        request=CreateExportJobSerializer,
        responses={
            200: ExportJobSerializer,
            400: get_error_schema(
                [
                    "ERROR_USER_NOT_IN_GROUP",
                    "ERROR_REQUEST_BODY_VALIDATION",
                    "ERROR_TABLE_ONLY_EXPORT_UNSUPPORTED",
                    "ERROR_VIEW_UNSUPPORTED_FOR_EXPORT_TYPE",
                    "ERROR_VIEW_NOT_IN_TABLE",
                    "ERROR_FILTER_FIELD_NOT_FOUND",
                    "ERROR_VIEW_FILTER_TYPE_DOES_NOT_EXIST",
                    "ERROR_VIEW_FILTER_TYPE_UNSUPPORTED_FIELD",
                    "ERROR_ORDER_BY_FIELD_NOT_FOUND",
                    "ERROR_ORDER_BY_FIELD_NOT_POSSIBLE",
                ]
            ),
            404: get_error_schema(
                ["ERROR_TABLE_DOES_NOT_EXIST", "ERROR_VIEW_DOES_NOT_EXIST"]
            ),
        },
    )
    @transaction.atomic
    @map_exceptions(
        {
            UserNotInWorkspace: ERROR_USER_NOT_IN_GROUP,
            TableDoesNotExist: ERROR_TABLE_DOES_NOT_EXIST,
            ViewDoesNotExist: ERROR_VIEW_DOES_NOT_EXIST,
            TableOnlyExportUnsupported: ERROR_TABLE_ONLY_EXPORT_UNSUPPORTED,
            ViewNotInTable: ERROR_VIEW_NOT_IN_TABLE,
            FilterFieldNotFound: ERROR_FILTER_FIELD_NOT_FOUND,
            ViewFilterTypeDoesNotExist: ERROR_VIEW_FILTER_TYPE_DOES_NOT_EXIST,
            ViewFilterTypeNotAllowedForField: ERROR_VIEW_FILTER_TYPE_UNSUPPORTED_FIELD,
            OrderByFieldNotFound: ERROR_ORDER_BY_FIELD_NOT_FOUND,
            OrderByFieldNotPossible: ERROR_ORDER_BY_FIELD_NOT_POSSIBLE,
            ViewGroupByFieldNotSupported: ERROR_VIEW_GROUP_BY_FIELD_NOT_SUPPORTED,
        }
    )
    def post(self, request, table_id):
        """
        Starts a new export job for the provided table, view, export type and options.
        """

        table = TableHandler().get_table(table_id)

        option_data = _validate_options(request.data)

        view_id = option_data.pop("view_id", None)
        view = (
            ViewHandler().get_view_as_user(request.user, view_id) if view_id else None
        )

        job = ExportHandler.create_and_start_new_job(
            request.user, table, view, option_data
        )
        return Response(ExportJobSerializer(job).data)


class ExportJobView(APIView):
    permission_classes = (IsAuthenticated,)

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="job_id",
                location=OpenApiParameter.PATH,
                type=OpenApiTypes.INT,
                description="The job id to lookup information about.",
            )
        ],
        tags=["Database table export"],
        operation_id="get_export_job",
        description=(
            "Returns information such as export progress and state or the url of the "
            "exported file for the specified export job, only if the requesting user "
            "has access."
        ),
        request=None,
        responses={
            200: ExportJobSerializer,
            404: get_error_schema(["ERROR_EXPORT_JOB_DOES_NOT_EXIST"]),
        },
    )
    @transaction.atomic
    @map_exceptions(
        {
            ExportJobDoesNotExistException: ERROR_EXPORT_JOB_DOES_NOT_EXIST,
        }
    )
    def get(self, request, job_id):
        """
        Retrieves the specified export job.
        """

        try:
            job = ExportJob.objects.get(id=job_id, user_id=request.user.id)
        except ExportJob.DoesNotExist:
            raise ExportJobDoesNotExistException()

        return Response(ExportJobSerializer(job).data)


class ExportJobDownloadView(APIView):
    """
    Streams the exported file straight out of the storage.

    The file is never linked to at a media URL: in a container deployment that URL is
    either served by nothing at all, or it is a presigned object storage link pointing
    at an address the browser cannot reach. Going through the API works in every
    deployment, at the cost of the bytes passing through this process.
    """

    authentication_classes = [DownloadTokenAuthentication] + list(
        APIView.authentication_classes
    )
    permission_classes = (IsAuthenticated,)

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="job_id",
                location=OpenApiParameter.PATH,
                type=OpenApiTypes.INT,
                description="The id of the export job to download the file of.",
            ),
            OpenApiParameter(
                name="dl",
                location=OpenApiParameter.QUERY,
                type=OpenApiTypes.STR,
                description=(
                    "The name the browser should save the file as. The stored file "
                    "name is a uuid, so the readable name is passed here."
                ),
            ),
            OpenApiParameter(
                name="token",
                location=OpenApiParameter.QUERY,
                type=OpenApiTypes.STR,
                description=(
                    "A signed download token, as returned in `download_url`. Lets a "
                    "browser download through a plain link, which cannot carry an "
                    "Authorization header. A regular JWT works as well."
                ),
            ),
        ],
        tags=["Database table export"],
        operation_id="download_export_job_file",
        description=(
            "Downloads the file of a finished export job, streamed from the server's "
            "file storage. Returns `ERROR_EXPORT_FILE_EXPIRED` when the export is "
            "past its expiry, and `ERROR_EXPORT_FILE_MISSING_FROM_STORAGE` or "
            "`ERROR_STORAGE_UNAVAILABLE` when the server cannot reach its own file "
            "storage."
        ),
        request=None,
        responses={
            200: OpenApiTypes.BINARY,
            401: get_error_schema(
                ["ERROR_DOWNLOAD_TOKEN_INVALID", "ERROR_DOWNLOAD_TOKEN_EXPIRED"]
            ),
            404: get_error_schema(["ERROR_EXPORT_JOB_DOES_NOT_EXIST"]),
            410: get_error_schema(["ERROR_EXPORT_FILE_EXPIRED"]),
            500: get_error_schema(["ERROR_EXPORT_FILE_MISSING_FROM_STORAGE"]),
            503: get_error_schema(["ERROR_STORAGE_UNAVAILABLE"]),
        },
    )
    @map_exceptions(
        {
            ExportJobDoesNotExistException: ERROR_EXPORT_JOB_DOES_NOT_EXIST,
            **DOWNLOAD_EXCEPTIONS,
        }
    )
    def get(self, request, job_id):
        return self._serve(request, job_id, head_only=False)

    @map_exceptions(
        {
            ExportJobDoesNotExistException: ERROR_EXPORT_JOB_DOES_NOT_EXIST,
            **DOWNLOAD_EXCEPTIONS,
        }
    )
    def head(self, request, job_id):
        """
        Answers the client's preflight: the same checks, without the body, so a
        download that cannot work is reported as a message instead of dumping an
        error page where the file was supposed to be.
        """

        return self._serve(request, job_id, head_only=True)

    def _serve(self, request, job_id, head_only):
        try:
            job = ExportJob.objects.get(id=job_id, user_id=request.user.id)
        except ExportJob.DoesNotExist:
            raise ExportJobDoesNotExistException()

        storage_path = (
            ExportHandler.export_file_path(job.exported_file_name)
            if job.exported_file_name
            else None
        )

        return serve_export_file(
            request,
            download_type=TABLE_EXPORT_DOWNLOAD,
            object_id=job.id,
            storage_path=storage_path,
            download_name=sanitize_download_name(
                request.GET.get("dl", ""), job.exported_file_name or "export"
            ),
            expired=ExportHandler.is_export_expired(job),
            expiry_message=(
                "This export is no longer available. Exports are kept for "
                f"{settings.EXPORT_FILE_EXPIRE_MINUTES} minutes, after which the file "
                "is removed. Please run the export again."
            ),
            head_only=head_only,
        )
