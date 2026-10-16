import hashlib
import json
import os
import re
from contextlib import nullcontext
from datetime import datetime, timedelta
from datetime import timezone as dt_timezone
from tempfile import SpooledTemporaryFile
from typing import IO, Any, Dict, List, Optional
from zipfile import BadZipFile, ZipFile

from django.contrib.auth.models import AbstractUser
from django.core.files.storage import Storage
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from loguru import logger

from baserow.core.data_destinations.config import PURPOSE_BACKUP
from baserow.core.data_destinations.exceptions import InvalidDataDestinationKey
from baserow.core.data_destinations.handler import DataDestinationHandler
from baserow.core.exceptions import PermissionException, WorkspaceDoesNotExist
from baserow.core.handler import CoreHandler
from baserow.core.import_export.handler import (
    MANIFEST_NAME,
    SIGNATURE_NAME,
    ImportExportHandler,
)
from baserow.core.job_types import ImportApplicationsJobType
from baserow.core.jobs.registries import job_type_registry
from baserow.core.models import (
    WORKSPACE_USER_PERMISSION_ADMIN,
    ImportApplicationsJob,
    ImportExportResource,
    ImportExportTrustedSource,
    WorkspaceUser,
)
from baserow.core.operations import (
    CreateApplicationsWorkspaceOperationType,
    ExportWorkspaceOperationType,
)
from baserow.core.storage import get_default_storage
from baserow.version import VERSION

from .exceptions import (
    RemoteBackupCorrupted,
    RemoteBackupDoesNotExist,
    RemoteBackupRestoreNotAllowed,
    RemoteBackupTrustNotAllowed,
)
from .models import BackupSchedule, ExportApplicationsToDestinationJob

BACKUPS_PREFIX = "backups"
ARCHIVE_SUFFIX = ".zip"
SIDECAR_SUFFIX = ".zip.json"
SIDECAR_FORMAT_VERSION = 1
# An archive without a sidecar is an incomplete upload, but it may also be an upload
# that is still running. Only the ones older than this are swept by remote retention.
ORPHAN_ARCHIVE_MIN_AGE = timedelta(hours=24)
COPY_CHUNK_SIZE = 1024 * 1024
# Archives up to this size are restored in memory, larger ones spill to disk.
RESTORE_MEMORY_LIMIT = 64 * 1024 * 1024
ARCHIVE_KEY_PATTERN = re.compile(
    rf"^{BACKUPS_PREFIX}/workspace=(?P<workspace_id>\d+)/[^/]+{re.escape(ARCHIVE_SUFFIX)}$"
)


def _sha256_of(handle: IO[bytes]) -> str:
    digest = hashlib.sha256()
    for chunk in iter(lambda: handle.read(COPY_CHUNK_SIZE), b""):
        digest.update(chunk)
    return digest.hexdigest()


class BackupDestinationHandler:
    """
    Ships backup archives to an env-declared data destination and brings them back.

    Every archive is written as `backups/workspace=<id>/<timestamp>_<uuid>.zip` with a
    JSON sidecar next to it. The sidecar is written last, so an archive without one is
    an incomplete upload and is ignored. The sidecar carries everything needed to list
    and restore the backup on a fresh instance, where the originating database is
    gone.

    Several instances may share a destination: retention only ever deletes the backups
    this instance made, and only staff may restore a backup made by another instance, and a member only
    sees and restores their own backups unless they are a workspace admin.
    """

    def __init__(self):
        self.destinations = DataDestinationHandler()

    def get_archive_key(
        self, workspace_id: int, created_on: datetime, resource_uuid: Any
    ) -> str:
        timestamp = created_on.astimezone(dt_timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        return (
            f"{BACKUPS_PREFIX}/workspace={workspace_id}/"
            f"{timestamp}_{resource_uuid}{ARCHIVE_SUFFIX}"
        )

    def get_sidecar_key(self, archive_key: str) -> str:
        return archive_key + ".json"

    def read_archive_metadata(self, handle: IO[bytes]) -> Dict[str, Any]:
        """
        Extracts the applications, configuration and signing key from an archive.

        :param handle: A seekable binary handle of the zip archive.
        :raises RemoteBackupCorrupted: When the archive is not a valid export.
        :return: The metadata stored in the sidecar.
        """

        try:
            with ZipFile(handle, "r") as zip_file:
                manifest = json.loads(zip_file.read(MANIFEST_NAME))
                signature = (
                    json.loads(zip_file.read(SIGNATURE_NAME))
                    if SIGNATURE_NAME in zip_file.namelist()
                    else {}
                )
        except (BadZipFile, KeyError, ValueError) as exc:
            raise RemoteBackupCorrupted(f"The archive is not a valid export: {exc}")

        applications = [
            {
                "id": item.get("id"),
                "name": item.get("name"),
                "type": application_type,
            }
            for application_type, group in manifest.get("applications", {}).items()
            for item in group.get("items", [])
        ]

        return {
            "applications": applications,
            "only_structure": bool(
                manifest.get("configuration", {}).get("only_structure", False)
            ),
            "public_key_pem": signature.get("public_key_pem") or "",
            "export_baserow_version": manifest.get("baserow_version"),
        }

    def upload_archive(self, job: ExportApplicationsToDestinationJob) -> str:
        """
        Uploads the archive of a finished export to its destination, followed by the
        sidecar that marks the upload as complete.

        :param job: The export job, its resource must already be set.
        :return: The key of the uploaded archive.
        """

        destination = self.destinations.get_destination(
            job.destination, purpose=PURPOSE_BACKUP
        )
        storage = self.destinations.get_storage(destination)
        source_storage = get_default_storage()
        resource = job.resource
        export_path = ImportExportHandler().get_export_storage_path(
            resource.get_archive_name()
        )

        archive_key = self.get_archive_key(
            job.workspace_id, timezone.now(), resource.uuid
        )

        with source_storage.open(export_path, "rb") as source:
            sha256 = _sha256_of(source)
            source.seek(0)
            metadata = self.read_archive_metadata(source)
            source.seek(0)
            self.destinations.save_file(storage, archive_key, source)

        workspace = job.workspace
        sidecar = {
            "format_version": SIDECAR_FORMAT_VERSION,
            "archive_key": archive_key,
            "instance_id": CoreHandler().get_settings().instance_id,
            "baserow_version": VERSION,
            "workspace": {
                "id": job.workspace_id,
                "name": workspace.name if workspace else None,
            },
            "schedule_id": job.backup_schedule_id,
            "created_on": timezone.now().isoformat(),
            "created_by": job.user.email if job.user_id else None,
            "created_by_id": job.user_id,
            "size": resource.size,
            "sha256": sha256,
            **metadata,
        }
        try:
            self.destinations.write_json(
                storage, self.get_sidecar_key(archive_key), sidecar
            )
        except Exception:
            # An archive without a sidecar is invisible garbage, don't leave it.
            try:
                self.destinations.delete_keys(storage, [archive_key])
            except Exception as exc:
                logger.warning(
                    "Could not delete the archive {key} after its sidecar failed: "
                    "{error}",
                    key=archive_key,
                    error=exc,
                )
            raise

        job.remote_key = archive_key
        job.save(update_fields=["remote_key"])

        return archive_key

    def list_backups(
        self, destination_name: str, workspace_id: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Lists the complete uploads on a destination, without any permission check.
        Meant for the periodic retention task and management commands.

        :param destination_name: The name of the data destination.
        :param workspace_id: Only the backups of this workspace, None for all.
        :return: The sidecars, each with its archive `key`, most recent first.
        """

        destination = self.destinations.get_destination(
            destination_name, purpose=PURPOSE_BACKUP
        )
        storage = self.destinations.get_storage(destination)
        keys = self._list_keys(storage, workspace_id)
        return self._read_sidecars(storage, keys)

    def _list_keys(self, storage: Storage, workspace_id: Optional[int]) -> List[str]:
        prefix = (
            f"{BACKUPS_PREFIX}/workspace={workspace_id}"
            if workspace_id is not None
            else BACKUPS_PREFIX
        )
        return self.destinations.list_keys(storage, prefix)

    def _read_sidecars(self, storage: Storage, keys: List[str]) -> List[Dict[str, Any]]:
        backups = []
        for key in keys:
            if not key.endswith(SIDECAR_SUFFIX):
                continue
            try:
                sidecar = self.destinations.read_json(storage, key)
            except (OSError, ValueError) as exc:
                logger.warning(
                    "Skipping unreadable backup sidecar {key}: {error}",
                    key=key,
                    error=exc,
                )
                continue
            if not isinstance(sidecar, dict):
                logger.warning(
                    "Skipping backup sidecar {key}: it is not a JSON object.",
                    key=key,
                )
                continue
            # Trust the key the sidecar was found at, not the one it claims.
            sidecar["key"] = key[: -len(".json")]
            backups.append(sidecar)

        backups.sort(
            key=lambda backup: str(backup.get("created_on") or ""), reverse=True
        )
        return backups

    def _sweep_orphan_archives(self, storage: Storage, keys: List[str]) -> int:
        """
        Deletes the archives that have no sidecar and are older than
        `ORPHAN_ARCHIVE_MIN_AGE`. They are the leftovers of uploads that died before
        the sidecar was written.

        An orphan carries no instance id, so it cannot be attributed to an instance
        on a shared destination. The age threshold is what makes the sweep safe: the
        sidecar is written right after the archive becomes visible (S3 multipart
        objects only appear once complete), so an archive that is still sidecar-less
        a day later is abandoned.

        :param storage: The destination storage.
        :param keys: Every key under the workspace prefix.
        :return: The number of orphan archives deleted.
        """

        key_set = set(keys)
        cutoff = timezone.now() - ORPHAN_ARCHIVE_MIN_AGE
        deleted = 0
        for key in keys:
            if not key.endswith(ARCHIVE_SUFFIX) or self.get_sidecar_key(key) in key_set:
                continue
            try:
                modified = storage.get_modified_time(key)
            except OSError, NotImplementedError, ValueError:
                continue
            if timezone.is_naive(modified):
                modified = timezone.make_aware(modified, dt_timezone.utc)
            if modified >= cutoff:
                continue
            try:
                self.destinations.delete_keys(storage, [key])
            except OSError as exc:
                logger.warning(
                    "Could not delete the orphan archive {key}: {error}",
                    key=key,
                    error=exc,
                )
                continue
            logger.info("Deleted the orphan backup archive {key}.", key=key)
            deleted += 1
        return deleted

    def list_remote_backups(
        self, user: AbstractUser, workspace_id: int, destination_name: str
    ) -> List[Dict[str, Any]]:
        """
        Lists the backups of a workspace that are available on a destination.

        Staff see everything on the destination. Anyone else only sees the backups this
        instance made, and a member who is not a workspace admin only the ones they
        made themselves.

        :param user: The user on whose behalf the backups are listed.
        :param workspace_id: The workspace the backups were made of.
        :param destination_name: The name of the data destination.
        :return: The sidecars of the complete uploads, most recent first.
        """

        workspace = CoreHandler().get_workspace(workspace_id)
        CoreHandler().check_permissions(
            user,
            ExportWorkspaceOperationType.type,
            workspace=workspace,
            context=workspace,
        )

        backups = self.list_backups(destination_name, workspace_id)

        if user.is_staff:
            return backups

        instance_id = CoreHandler().get_settings().instance_id
        is_admin = self._is_workspace_admin(user, workspace_id)
        return [
            backup
            for backup in backups
            if backup.get("instance_id") == instance_id
            and (is_admin or self._is_made_by(user, backup))
        ]

    def _is_workspace_admin(self, user: AbstractUser, workspace_id: int) -> bool:
        return WorkspaceUser.objects.filter(
            user_id=user.id,
            workspace_id=workspace_id,
            permissions=WORKSPACE_USER_PERMISSION_ADMIN,
        ).exists()

    def _is_made_by(self, user: AbstractUser, sidecar: Dict[str, Any]) -> bool:
        """
        Whether the user made the backup. Sidecars written before `created_by_id`
        existed are matched on the email they recorded.
        """

        created_by_id = sidecar.get("created_by_id")
        if created_by_id is not None:
            return created_by_id == user.id

        created_by = sidecar.get("created_by")
        return bool(created_by) and created_by == user.email

    def apply_remote_retention(self, schedule: BackupSchedule) -> int:
        """
        Deletes the uploaded backups of a schedule that fall outside its retention
        window. Only backups this schedule made are considered. Schedule ids are only
        unique per instance, so backups of another instance sharing the destination
        are never touched.

        :param schedule: The schedule whose retention rules are applied.
        :return: The number of remote backups deleted.
        """

        if not schedule.destination:
            return 0

        destination = self.destinations.get_destination(
            schedule.destination, purpose=PURPOSE_BACKUP
        )
        storage = self.destinations.get_storage(destination)
        keys = self._list_keys(storage, schedule.workspace_id)
        self._sweep_orphan_archives(storage, keys)

        if schedule.keep_last is None and schedule.keep_days is None:
            return 0

        instance_id = CoreHandler().get_settings().instance_id
        backups = [
            backup
            for backup in self._read_sidecars(storage, keys)
            if backup.get("schedule_id") == schedule.id
            and backup.get("instance_id") == instance_id
        ]

        to_delete = {}
        if schedule.keep_last is not None:
            for backup in backups[schedule.keep_last :]:
                to_delete[backup["key"]] = backup
        if schedule.keep_days is not None:
            cutoff = timezone.now() - timedelta(days=schedule.keep_days)
            for backup in backups:
                raw = backup.get("created_on")
                if not isinstance(raw, str):
                    continue
                try:
                    created_on = parse_datetime(raw)
                except ValueError:
                    continue
                if created_on is not None and created_on < cutoff:
                    to_delete[backup["key"]] = backup

        for key in to_delete:
            # The archive goes first: a sidecar without an archive is still listed and
            # would be retried, an archive without a sidecar is invisible garbage.
            self.destinations.delete_keys(storage, [key, self.get_sidecar_key(key)])

        return len(to_delete)

    def restore_remote_backup(
        self,
        user: AbstractUser,
        workspace_id: int,
        destination_name: str,
        key: str,
        application_ids: Optional[List[int]] = None,
        trust_public_key: bool = False,
        sync: bool = False,
    ) -> ImportApplicationsJob:
        """
        Downloads a backup from a destination and starts restoring it into a
        workspace. The applications are installed as new applications.

        :param user: The user on whose behalf the restore is made.
        :param workspace_id: The workspace to restore into.
        :param destination_name: The name of the data destination.
        :param key: The key of the archive, as returned by the listing.
        :param application_ids: The applications from the archive to restore. None
            means all of them.
        :param trust_public_key: Trust the key the archive was signed with, which is
            needed when it was made by another instance. Requires a staff user and a
            destination that allows it.
        :raises InvalidDataDestinationKey: When the key is not a backup archive key.
        :raises RemoteBackupDoesNotExist: When the archive or its sidecar is missing.
        :raises RemoteBackupCorrupted: When the archive does not match its sidecar.
        :raises RemoteBackupTrustNotAllowed: When trusting the key is not permitted.
        :raises RemoteBackupRestoreNotAllowed: When a non-staff user restores a backup
            of another instance, of a workspace they cannot export, or, unless they
            are a workspace admin, one made by somebody else.
        :param sync: Run the import in the current process instead of a worker.
        :return: The started import job.
        """

        workspace = CoreHandler().get_workspace(workspace_id)
        CoreHandler().check_permissions(
            user,
            CreateApplicationsWorkspaceOperationType.type,
            workspace=workspace,
            context=workspace,
        )

        destination = self.destinations.get_destination(
            destination_name, purpose=PURPOSE_BACKUP
        )
        key = self.destinations.normalize_key(key)
        key_match = ARCHIVE_KEY_PATTERN.match(key)
        if key_match is None:
            raise InvalidDataDestinationKey(f"The key '{key}' is not a backup archive.")

        if trust_public_key and (
            not user.is_staff or not destination.allow_trust_public_key
        ):
            raise RemoteBackupTrustNotAllowed(
                "Trusting the signing key of a remote backup requires a staff user and "
                "a destination with `allow_trust_public_key` enabled."
            )

        storage = self.destinations.get_storage(destination)
        sidecar_key = self.get_sidecar_key(key)
        if not storage.exists(key) or not storage.exists(sidecar_key):
            raise RemoteBackupDoesNotExist(f"The backup '{key}' is not available.")
        try:
            sidecar = self.destinations.read_json(storage, sidecar_key)
        except (OSError, ValueError) as exc:
            raise RemoteBackupCorrupted(f"The sidecar of '{key}' is unreadable: {exc}")
        if not isinstance(sidecar, dict):
            raise RemoteBackupCorrupted(f"The sidecar of '{key}' is not an object.")

        if not user.is_staff:
            self._check_can_read_backup(
                user, int(key_match.group("workspace_id")), sidecar
            )

        # Refuse before downloading anything when the user cannot start the import.
        job_type_registry.get(ImportApplicationsJobType.type).can_schedule_or_raise(
            ImportApplicationsJob(user=user)
        )

        from .handler import BackupHandler

        # Everything slow (download, checksum, upload into the import storage) runs
        # outside a transaction so no database connection is held open meanwhile.
        resource = None
        trusted_name = None
        known_sources: set = set()
        try:
            with SpooledTemporaryFile(max_size=RESTORE_MEMORY_LIMIT) as archive:
                with storage.open(key, "rb") as source:
                    for chunk in iter(lambda: source.read(COPY_CHUNK_SIZE), b""):
                        archive.write(chunk)

                archive.seek(0)
                if _sha256_of(archive) != sidecar.get("sha256"):
                    raise RemoteBackupCorrupted(
                        f"The archive '{key}' does not match its recorded checksum."
                    )

                if trust_public_key:
                    archive.seek(0)
                    public_key_pem = self._verify_archive_key(archive, sidecar)
                    # The signature is checked when the resource is created, so the
                    # key has to be trusted before that. It is removed again below
                    # when the restore cannot start.
                    known_sources = set(
                        ImportExportTrustedSource.objects.values_list("id", flat=True)
                    )
                    trusted_name = self._trust_archive_key(
                        user, destination.name, public_key_pem, sidecar
                    )

                archive.seek(0)
                resource = ImportExportHandler().create_resource_from_file(
                    user, os.path.basename(key), archive
                )

            # A synchronous restore keeps the per-application transactions of the
            # import, so it must not be wrapped in one.
            with transaction.atomic() if not sync else nullcontext():
                return BackupHandler().start_restore(
                    user,
                    workspace_id,
                    resource.id,
                    application_ids=application_ids,
                    sync=sync,
                )
        except Exception:
            if resource is not None:
                self._discard_resource(resource)
            if trusted_name is not None:
                ImportExportTrustedSource.objects.filter(name=trusted_name).exclude(
                    id__in=known_sources
                ).delete()
            raise

    def _discard_resource(self, resource: ImportExportResource):
        """
        Removes the resource of a restore that could not be started, together with its
        file. Does nothing when an import job already references it.
        """

        try:
            if ImportApplicationsJob.objects.filter(resource_id=resource.id).exists():
                return
            try:
                handler = ImportExportHandler()
                get_default_storage().delete(
                    handler.get_import_storage_path(resource.get_archive_name())
                )
            except Exception as exc:
                logger.warning(
                    "Could not delete the file of discarded resource {id}: {error}",
                    id=resource.id,
                    error=exc,
                )
            ImportExportResource.objects_and_trash.filter(id=resource.id).delete()
        except Exception as exc:
            logger.warning(
                "Could not discard resource {id}: {error}", id=resource.id, error=exc
            )

    def _check_can_read_backup(
        self, user: AbstractUser, source_workspace_id: int, sidecar: Dict[str, Any]
    ):
        """
        Checks that a non-staff user may read the data of a backup: it must have been
        made by this instance, of a workspace the user can export, and by the user
        themselves unless they are an admin of that workspace. Listing requires the
        same, so a user cannot restore a backup they could not have listed.
        """

        if sidecar.get("instance_id") != CoreHandler().get_settings().instance_id:
            raise RemoteBackupRestoreNotAllowed(
                "Only staff can restore a backup made by another instance."
            )

        try:
            source_workspace = CoreHandler().get_workspace(source_workspace_id)
            CoreHandler().check_permissions(
                user,
                ExportWorkspaceOperationType.type,
                workspace=source_workspace,
                context=source_workspace,
            )
        except WorkspaceDoesNotExist, PermissionException:
            raise RemoteBackupRestoreNotAllowed(
                "You can only restore backups of workspaces you can export."
            )

        if not self._is_workspace_admin(
            user, source_workspace_id
        ) and not self._is_made_by(user, sidecar):
            raise RemoteBackupRestoreNotAllowed(
                "You can only restore the backups you made, unless you are an admin "
                "of the workspace."
            )

    def _verify_archive_key(self, archive: IO[bytes], sidecar: Dict[str, Any]) -> str:
        """
        Returns the key an archive was signed with, which must equal the one recorded
        in the sidecar, so a swapped archive cannot smuggle in a key of its own.
        """

        public_key_pem = self.read_archive_metadata(archive)["public_key_pem"]
        if not public_key_pem or public_key_pem != sidecar.get("public_key_pem"):
            raise RemoteBackupCorrupted(
                "The signing key of the archive does not match its recorded key."
            )
        return public_key_pem

    def _trust_archive_key(
        self,
        user: AbstractUser,
        destination_name: str,
        public_key_pem: str,
        sidecar: Dict[str, Any],
    ) -> str:
        """
        Registers a verified signing key as a trusted import source.

        :return: The name the key was registered under.
        """

        name = f"destination:{destination_name}:{sidecar.get('instance_id') or ''}"
        ImportExportHandler().add_trusted_public_key(name[:255], public_key_pem)
        logger.warning(
            "User {user_id} trusted the backup signing key of {name}.",
            user_id=user.id,
            name=name,
        )
        return name[:255]
