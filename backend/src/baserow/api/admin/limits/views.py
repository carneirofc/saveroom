from django.conf import settings

from drf_spectacular.utils import extend_schema
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView

from .serializers import AdminOperationalLimitsSerializer


class AdminOperationalLimitsView(APIView):
    permission_classes = (IsAdminUser,)

    @extend_schema(
        tags=["Admin"],
        operation_id="admin_operational_limits",
        description=(
            "Returns the retention and time limits this instance enforces, so an "
            "admin can see how long data is kept before it is cleaned up. These "
            "values come from the environment and cannot be changed over the API; "
            "they are informational only."
        ),
        responses={
            200: AdminOperationalLimitsSerializer,
            401: None,
        },
    )
    def get(self, request):
        return Response(
            AdminOperationalLimitsSerializer(
                {
                    "hours_until_trash_permanently_deleted": (
                        settings.HOURS_UNTIL_TRASH_PERMANENTLY_DELETED
                    ),
                    "export_file_expire_minutes": settings.EXPORT_FILE_EXPIRE_MINUTES,
                    "snapshot_expiration_time_days": (
                        settings.BASEROW_SNAPSHOT_EXPIRATION_TIME_DAYS
                    ),
                    "max_snapshots_per_workspace": (
                        settings.BASEROW_MAX_SNAPSHOTS_PER_GROUP
                    ),
                    "user_log_entry_retention_days": (
                        settings.BASEROW_USER_LOG_ENTRY_RETENTION_DAYS
                    ),
                    "row_history_retention_days": (
                        settings.BASEROW_ROW_HISTORY_RETENTION_DAYS
                    ),
                    "job_soft_time_limit_seconds": settings.BASEROW_JOB_SOFT_TIME_LIMIT,
                    "job_expiration_time_limit_minutes": (
                        settings.BASEROW_JOB_EXPIRATION_TIME_LIMIT
                    ),
                    "import_export_resource_removal_after_days": (
                        settings.BASEROW_IMPORT_EXPORT_RESOURCE_REMOVAL_AFTER_DAYS
                    ),
                }
            ).data
        )
