from typing import Any, Dict

from django.contrib.auth.models import AbstractUser

from rest_framework import serializers

from baserow.api.data_destinations.errors import (
    ERROR_DATA_DESTINATION_DOES_NOT_EXIST,
    ERROR_DATA_DESTINATION_PURPOSE_NOT_ALLOWED,
)
from baserow.core.data_destinations.config import PURPOSE_BACKUP
from baserow.core.data_destinations.exceptions import (
    DataDestinationDoesNotExist,
    DataDestinationPurposeNotAllowed,
)
from baserow.core.data_destinations.handler import DataDestinationHandler
from baserow.core.job_types import ExportApplicationsJobType
from baserow.core.utils import Progress

from .models import ExportApplicationsToDestinationJob

# The share of the job progress the upload represents, the export takes the rest.
UPLOAD_PROGRESS_PERCENTAGE = 10


class ExportApplicationsToDestinationJobType(ExportApplicationsJobType):
    """
    Exports applications exactly like `ExportApplicationsJobType`, then uploads the
    archive to a data destination. A failed upload fails the job, while the archive
    stays available on the instance storage.

    Scheduled backups always use this job type, so they remember the schedule that
    made them and its retention only ever considers its own backups. Without a
    destination such a backup stays on the instance storage only.
    """

    type = "export_applications_to_destination"
    model_class = ExportApplicationsToDestinationJob
    max_count = 1

    api_exceptions_map = {
        **ExportApplicationsJobType.api_exceptions_map,
        DataDestinationDoesNotExist: ERROR_DATA_DESTINATION_DOES_NOT_EXIST,
        DataDestinationPurposeNotAllowed: ERROR_DATA_DESTINATION_PURPOSE_NOT_ALLOWED,
    }

    job_exceptions_map = {
        **ExportApplicationsJobType.job_exceptions_map,
        DataDestinationDoesNotExist: "The data destination is not configured.",
    }

    request_serializer_field_names = [
        *ExportApplicationsJobType.request_serializer_field_names,
        "destination",
    ]
    request_serializer_field_overrides = {
        **ExportApplicationsJobType.request_serializer_field_overrides,
        "destination": serializers.CharField(
            max_length=100,
            help_text="The name of the data destination to upload the archive to.",
        ),
    }

    serializer_field_names = [
        *ExportApplicationsJobType.serializer_field_names,
        "destination",
        "remote_key",
    ]

    def prepare_values(
        self, values: Dict[str, Any], user: AbstractUser
    ) -> Dict[str, Any]:
        destination = values.get("destination") or ""
        if destination or values.get("backup_schedule") is None:
            DataDestinationHandler().get_destination(
                destination, purpose=PURPOSE_BACKUP
            )

        prepared = super().prepare_values(values, user)
        prepared["destination"] = destination

        if values.get("backup_schedule") is not None:
            prepared["backup_schedule"] = values["backup_schedule"]

        return prepared

    def run(self, job: ExportApplicationsToDestinationJob, progress: Progress):
        from .destination import BackupDestinationHandler

        export_progress = progress.create_child(
            represents_progress=progress.total
            * (100 - UPLOAD_PROGRESS_PERCENTAGE)
            // 100,
            total=progress.total,
        )
        super().run(job, export_progress)

        if job.destination:
            BackupDestinationHandler().upload_archive(job)
        progress.set_progress(progress.total)
