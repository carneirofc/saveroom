from django.conf import settings

from drf_spectacular.utils import extend_schema
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView

from baserow.version import VERSION

from .serializers import AdminBuildInfoSerializer


class AdminBuildInfoView(APIView):
    permission_classes = (IsAdminUser,)

    @extend_schema(
        tags=["Admin"],
        operation_id="admin_build_info",
        description=(
            "Returns the build this instance is running: the release tag, the git "
            "commit and the build date baked into the image. They identify the "
            "exact source behind a deployment, which is what a version number "
            "alone cannot do. A development build reports empty values."
        ),
        responses={
            200: AdminBuildInfoSerializer,
            401: None,
        },
    )
    def get(self, request):
        return Response(
            AdminBuildInfoSerializer(
                {
                    "version": settings.BASEROW_BUILD_VERSION,
                    "commit": settings.BASEROW_BUILD_COMMIT,
                    "build_date": settings.BASEROW_BUILD_DATE,
                    "baserow_version": VERSION,
                }
            ).data
        )
