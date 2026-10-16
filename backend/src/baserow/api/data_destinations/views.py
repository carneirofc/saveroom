from drf_spectacular.utils import extend_schema
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from baserow.api.api_clients.authentication import (
    ApiClientAuthentication,
    HasApiClientScope,
)
from baserow.core.data_destinations.handler import DataDestinationHandler

from .serializers import DataDestinationSerializer


class DataDestinationsView(APIView):
    authentication_classes = APIView.authentication_classes + [ApiClientAuthentication]
    permission_classes = (IsAuthenticated, HasApiClientScope)
    api_client_scopes = {"GET": "backup.read"}
    # Destinations are declared by the operator for the whole instance.
    api_client_workspace_independent = True

    @extend_schema(
        tags=["Data destinations"],
        operation_id="list_data_destinations",
        description=(
            "Lists the external data destinations declared by the instance operator. "
            "Only names, types and purposes are returned, never credentials or "
            "locations. Backup schedules and table export schedules reference a "
            "destination by its name."
        ),
        responses={200: DataDestinationSerializer(many=True)},
    )
    def get(self, request):
        destinations = DataDestinationHandler().list_destinations()
        return Response(DataDestinationSerializer(destinations, many=True).data)
