from django.conf import settings

from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from baserow.core.import_export.handler import ImportExportHandler

from .authentication import DownloadTokenAuthentication
from .handler import serve_export_file
from .tokens import WORKSPACE_EXPORT_DOWNLOAD


class BaseArchiveDownloadView(APIView):
    """
    Streams the archive of a workspace export or a backup straight out of the storage.

    The archive is never linked to at a media URL: in a container deployment that URL
    is either served by nothing at all, or it is a presigned object storage link
    pointing at an address the browser cannot reach. Going through the API works in
    every deployment, at the cost of the bytes passing through this process.

    Subclasses only decide how the job is looked up and which permissions apply; the
    resolution of the archive and the reporting of every way it can fail live here so
    all of them answer the same way.
    """

    authentication_classes = [DownloadTokenAuthentication] + list(
        APIView.authentication_classes
    )
    permission_classes = (IsAuthenticated,)
    download_type = WORKSPACE_EXPORT_DOWNLOAD

    def get_job(self, request, **kwargs):
        """
        Looks the export job up with the same scoping the listing endpoint uses.

        :param request: The request being served.
        :return: The `ExportApplicationsJob` whose archive is being downloaded.
        """

        raise NotImplementedError

    def get_token_object_id(self, job, **kwargs) -> int:
        """
        The id the download token is bound to. Backups are addressed by their resource
        id rather than the job id, so the link and the route agree on one identifier.
        """

        return job.id

    def serve(self, request, head_only=False, **kwargs):
        job = self.get_job(request, **kwargs)
        resource = getattr(job, "resource", None)

        # Two different names: the archive is stored under the bare name, while the
        # browser is offered the prefixed one the listing already shows.
        archive_name = resource.get_archive_name() if resource else None
        storage_path = (
            ImportExportHandler().export_file_path(archive_name)
            if archive_name
            else None
        )

        return serve_export_file(
            request,
            download_type=self.download_type,
            object_id=self.get_token_object_id(job, **kwargs),
            storage_path=storage_path,
            download_name=f"export_{archive_name}" if archive_name else "export.zip",
            expired=ImportExportHandler.is_export_expired(job),
            expiry_message=(
                "This archive is no longer available. Archives are kept for "
                f"{settings.BASEROW_IMPORT_EXPORT_RESOURCE_REMOVAL_AFTER_DAYS} days, "
                "after which the file is removed. Please create a new one."
            ),
            head_only=head_only,
        )
