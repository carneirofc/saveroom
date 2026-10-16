import csv

from django.http import StreamingHttpResponse

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView

from baserow.api.admin.views import AdminListingView
from baserow.api.pagination import PageNumberPaginationWithApproximateCount
from baserow.core.action.registries import action_type_registry
from baserow.core.audit_log.models import (
    AUTH_EVENT_TYPES,
    COMMAND_TYPE_CHOICES,
    AuditLogEntry,
)

from .serializers import AuditLogEntryFilterOptionsSerializer, AuditLogEntrySerializer

AUDIT_LOG_EXTRA_PARAMETERS = [
    OpenApiParameter(
        name="user_id",
        location=OpenApiParameter.QUERY,
        type=OpenApiTypes.INT,
        description="Only return entries performed by this user.",
    ),
    OpenApiParameter(
        name="workspace_id",
        location=OpenApiParameter.QUERY,
        type=OpenApiTypes.INT,
        description="Only return entries that took place in this workspace.",
    ),
    OpenApiParameter(
        name="action_type",
        location=OpenApiParameter.QUERY,
        type=OpenApiTypes.STR,
        description="Only return entries of this action type.",
    ),
    OpenApiParameter(
        name="command_type",
        location=OpenApiParameter.QUERY,
        type=OpenApiTypes.STR,
        description=(
            "Only return entries with this command type, one of DO, UNDO, REDO or AUTH."
        ),
    ),
    OpenApiParameter(
        name="created_after",
        location=OpenApiParameter.QUERY,
        type=OpenApiTypes.DATETIME,
        description="Only return entries created on or after this timestamp.",
    ),
    OpenApiParameter(
        name="created_before",
        location=OpenApiParameter.QUERY,
        type=OpenApiTypes.DATETIME,
        description="Only return entries created on or before this timestamp.",
    ),
]


class AuditLogEntryAdminView(AdminListingView):
    serializer_class = AuditLogEntrySerializer
    pagination_class = PageNumberPaginationWithApproximateCount
    search_fields = ["description", "user_email", "action_type"]
    sort_field_mapping = {
        "id": "id",
        "created_on": "created_on",
        "user_email": "user_email",
        "action_type": "action_type",
    }
    default_order_by = "-created_on"
    filters_field_mapping = {
        "user_id": "user_id",
        "workspace_id": "workspace_id",
        "action_type": "action_type",
        "command_type": "command_type",
        "created_after": "created_on__gte",
        "created_before": "created_on__lte",
    }

    def get_queryset(self, request):
        return AuditLogEntry.objects.select_related("user", "workspace")

    @extend_schema(
        tags=["Admin"],
        operation_id="admin_list_audit_log_entries",
        description="Lists the audit log entries, if the requesting user is staff.",
        **AdminListingView.get_extend_schema_parameters(
            "audit log entries",
            serializer_class,
            search_fields,
            sort_field_mapping,
            extra_parameters=AUDIT_LOG_EXTRA_PARAMETERS,
        ),
    )
    def get(self, request):
        return super().get(request)


class AuditLogEntryFilterOptionsView(APIView):
    permission_classes = (IsAdminUser,)

    @extend_schema(
        tags=["Admin"],
        operation_id="admin_get_audit_log_filter_options",
        description=(
            "Lists the values the `action_type` and `command_type` filters accept, so "
            "they can be offered as a choice instead of typed by hand."
        ),
        responses={200: AuditLogEntryFilterOptionsSerializer},
    )
    def get(self, request):
        # Read from the registry rather than from the entries themselves: the audit
        # log is permanent and unbounded, so a DISTINCT over it would grow more
        # expensive for the lifetime of the instance.
        action_types = sorted(action_type_registry.get_types() + AUTH_EVENT_TYPES)
        return Response(
            AuditLogEntryFilterOptionsSerializer(
                {
                    "action_types": action_types,
                    "command_types": [value for value, _ in COMMAND_TYPE_CHOICES],
                }
            ).data
        )


class AuditLogEntryExportView(APIView):
    permission_classes = (IsAdminUser,)

    def _filtered_queryset(self, request):
        view = AuditLogEntryAdminView()
        queryset = view.get_queryset(request)
        queryset = view.apply_filters(request.GET, queryset)
        queryset = view.apply_search(request.GET.get("search"), queryset)
        return view.apply_sorts_or_default_sort(request.GET.get("sorts"), queryset)

    @extend_schema(
        tags=["Admin"],
        operation_id="admin_export_audit_log_entries",
        description=(
            "Exports the filtered audit log entries as a CSV file, if the "
            "requesting user is staff."
        ),
        parameters=AUDIT_LOG_EXTRA_PARAMETERS,
        responses={200: OpenApiTypes.BINARY},
    )
    def get(self, request):
        queryset = self._filtered_queryset(request)
        fields = [
            "id",
            "created_on",
            "user_email",
            "workspace_id",
            "action_type",
            "command_type",
            "description",
            "ip_address",
        ]

        def rows():
            buffer = _CsvBuffer()
            writer = csv.writer(buffer)
            yield writer.writerow(fields)
            for entry in queryset.iterator():
                yield writer.writerow([getattr(entry, field) for field in fields])

        response = StreamingHttpResponse(rows(), content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="audit-log.csv"'
        return response


class _CsvBuffer:
    """A file-like object that returns what was just written, for streaming CSV
    rows one at a time without building the whole file in memory."""

    def write(self, value):
        return value
