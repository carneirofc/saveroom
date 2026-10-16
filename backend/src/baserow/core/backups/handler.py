from typing import TYPE_CHECKING, List, Optional

from django.contrib.auth.models import AbstractUser
from django.core.files.storage import Storage
from django.db.models import QuerySet

from baserow.core.import_export.exceptions import ImportExportResourceDoesNotExist
from baserow.core.import_export.handler import ImportExportHandler
from baserow.core.job_types import ExportApplicationsJobType, ImportApplicationsJobType
from baserow.core.jobs.constants import JOB_FINISHED
from baserow.core.jobs.handler import JobHandler
from baserow.core.models import (
    ExportApplicationsJob,
    ImportApplicationsJob,
    ImportExportResource,
)
from baserow.core.storage import (
    _create_storage_dir_if_missing_and_open,
    get_default_storage,
)

from .job_types import ExportApplicationsToDestinationJobType

if TYPE_CHECKING:
    from .models import BackupSchedule

COPY_CHUNK_SIZE = 1024 * 1024


class BackupHandler:
    """
    A thin, machine facing wrapper around the workspace import/export machinery.

    A backup is nothing more than a regular application export: an
    `ImportExportResource` holding a signed and checksummed archive, produced by an
    `ExportApplicationsJob`. Backing up a whole workspace and backing up a single
    application are the same operation with and without `application_ids`.
    """

    def start_backup(
        self,
        user: AbstractUser,
        workspace_id: int,
        application_ids: Optional[List[int]] = None,
        only_structure: bool = False,
        destination: Optional[str] = None,
        backup_schedule: Optional["BackupSchedule"] = None,
        sync: bool = False,
    ) -> ExportApplicationsJob:
        """
        Starts an asynchronous backup of a workspace or of a subset of its
        applications.

        :param user: The user on whose behalf the backup is made.
        :param workspace_id: The workspace to back up.
        :param application_ids: The applications to back up. None or an empty list
            means every application of the workspace.
        :param only_structure: If true the row data is left out of the archive.
        :param destination: The name of a data destination the archive is uploaded
            to once it is made. None keeps it on the instance storage only.
        :param backup_schedule: The schedule starting the backup, if any.
        :param sync: Run the job in the current process instead of a worker.
        :return: The started job.
        """

        if destination or backup_schedule is not None:
            return JobHandler().create_and_start_job(
                user,
                ExportApplicationsToDestinationJobType.type,
                sync=sync,
                workspace_id=workspace_id,
                application_ids=application_ids,
                only_structure=only_structure,
                destination=destination,
                backup_schedule=backup_schedule,
            )

        return JobHandler().create_and_start_job(
            user,
            ExportApplicationsJobType.type,
            sync=sync,
            workspace_id=workspace_id,
            application_ids=application_ids,
            only_structure=only_structure,
        )

    def list_backups(self, user: AbstractUser, workspace_id: int) -> QuerySet:
        """
        Lists the finished backups of a workspace that belong to the given user.

        :param user: The user on whose behalf the backups are listed.
        :param workspace_id: The workspace to list the backups of.
        :return: A queryset of finished export jobs with a valid resource.
        """

        return ImportExportHandler().list_exports(user, workspace_id)

    def get_backup(
        self, user: AbstractUser, workspace_id: int, resource_id: int
    ) -> ExportApplicationsJob:
        """
        Fetches a single backup of a workspace.

        :param user: The user on whose behalf the backup is requested.
        :param workspace_id: The workspace the backup belongs to.
        :param resource_id: The id of the resource holding the archive.
        :raises ImportExportResourceDoesNotExist: When there is no such backup for
            this user and workspace.
        :return: The export job describing the backup.
        """

        # `list_backups` returns a sliced queryset, which cannot be filtered further,
        # so the match is made in Python over that same bounded list.
        backup = next(
            (
                candidate
                for candidate in self.list_backups(user, workspace_id)
                if candidate.resource_id == int(resource_id)
            ),
            None,
        )

        if backup is None:
            raise ImportExportResourceDoesNotExist(
                f"The backup with resource id {resource_id} does not exist."
            )

        return backup

    def get_backup_for_download(
        self, user: AbstractUser, workspace_id: int, resource_id: int
    ) -> ExportApplicationsJob:
        """
        Fetches a backup for downloading.

        Unlike `get_backup` this does not require the archive to still be valid, so
        the download endpoint can tell a backup whose archive aged out apart from one
        that was never the user's. Use `ImportExportHandler.is_export_expired` to make
        that distinction.

        :param user: The user on whose behalf the backup is requested.
        :param workspace_id: The workspace the backup belongs to.
        :param resource_id: The id of the resource holding the archive.
        :raises ImportExportResourceDoesNotExist: When there is no such backup for
            this user and workspace.
        :return: The export job describing the backup.
        """

        handler = ImportExportHandler()
        handler.get_workspace_or_raise(user, workspace_id)

        backup = (
            ExportApplicationsJob.objects.filter(
                workspace_id=workspace_id,
                user=user,
                state=JOB_FINISHED,
                resource_id=resource_id,
            )
            .select_related("resource")
            .first()
        )

        if backup is None:
            raise ImportExportResourceDoesNotExist(
                f"The backup with resource id {resource_id} does not exist."
            )

        return backup

    def delete_backup(self, user: AbstractUser, resource_id: int):
        """
        Marks the archive of a backup for deletion. A periodic task removes the files
        and the record afterwards.

        :param user: The user on whose behalf the backup is deleted.
        :param resource_id: The id of the resource holding the archive.
        """

        ImportExportHandler().mark_resource_for_deletion(user, resource_id)

    def start_restore(
        self,
        user: AbstractUser,
        workspace_id: int,
        resource_id: int,
        application_ids: Optional[List[int]] = None,
        sync: bool = False,
    ) -> ImportApplicationsJob:
        """
        Starts an asynchronous restore of a backup into a workspace.

        The applications in the archive are installed as new applications, an existing
        application is never overwritten in place.

        :param user: The user on whose behalf the restore is made.
        :param workspace_id: The workspace to restore into.
        :param resource_id: The resource holding the archive to restore.
        :param application_ids: The applications from the archive to restore. None or
            an empty list means every application in the archive.
        :param sync: Run the job in the current process instead of a worker.
        :return: The started job.
        """

        self.make_archive_importable(user, resource_id)

        return JobHandler().create_and_start_job(
            user,
            ImportApplicationsJobType.type,
            sync=sync,
            workspace_id=workspace_id,
            resource_id=resource_id,
            application_ids=application_ids,
        )

    def make_archive_importable(
        self,
        user: AbstractUser,
        resource_id: int,
        storage: Optional[Storage] = None,
    ):
        """
        Copies the archive of a backup into the import directory when it is not there
        yet.

        Exporting writes to `EXPORT_FILES_DIRECTORY` while importing reads from
        `IMPORT_FILES_DIRECTORY`. An archive that was uploaded is already in the right
        place, one that this instance produced itself is not, and would otherwise be
        impossible to restore from.

        :param user: The user the resource must belong to.
        :param resource_id: The resource holding the archive.
        :param storage: The storage to use, defaults to the configured one.
        """

        resource = ImportExportResource.objects.filter(
            id=resource_id, created_by=user
        ).first()

        if resource is None:
            # The job type raises the proper error for this, keep the messages in one
            # place instead of duplicating them here.
            return

        storage = storage or get_default_storage()
        handler = ImportExportHandler()
        archive_name = resource.get_archive_name()

        import_path = handler.get_import_storage_path(archive_name)

        if storage.exists(import_path):
            return

        export_path = handler.get_export_storage_path(archive_name)

        if not storage.exists(export_path):
            raise ImportExportResourceDoesNotExist(
                f"The archive of resource {resource_id} is not available."
            )

        with storage.open(export_path, "rb") as source:
            with _create_storage_dir_if_missing_and_open(
                import_path, storage
            ) as target:
                for chunk in iter(lambda: source.read(COPY_CHUNK_SIZE), b""):
                    target.write(chunk)
