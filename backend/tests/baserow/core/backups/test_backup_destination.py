import hashlib
import json
import os
import time
import uuid
from unittest.mock import patch

from django.conf import settings
from django.core.management import call_command
from django.db import connection
from django.urls import reverse
from django.utils import timezone

import pytest
from rest_framework.status import HTTP_200_OK, HTTP_202_ACCEPTED, HTTP_404_NOT_FOUND

from baserow.core.backups.destination import BackupDestinationHandler
from baserow.core.backups.exceptions import (
    RemoteBackupCorrupted,
    RemoteBackupRestoreNotAllowed,
    RemoteBackupTrustNotAllowed,
)
from baserow.core.backups.handler import BackupHandler
from baserow.core.backups.models import ExportApplicationsToDestinationJob
from baserow.core.backups.schedule_handler import BackupScheduleHandler
from baserow.core.data_destinations.config import parse_data_destinations_env
from baserow.core.data_destinations.exceptions import InvalidDataDestinationKey
from baserow.core.data_destinations.handler import DataDestinationHandler
from baserow.core.handler import CoreHandler
from baserow.core.import_export.exceptions import (
    ImportExportResourceUntrustedSignature,
)
from baserow.core.import_export.handler import ImportExportHandler
from baserow.core.jobs.constants import JOB_FINISHED
from baserow.core.jobs.exceptions import MaxJobCountExceeded
from baserow.core.jobs.handler import JobHandler
from baserow.core.models import (
    Application,
    ImportApplicationsJob,
    ImportExportResource,
    ImportExportTrustedSource,
)


@pytest.fixture
def backup_destination(settings, tmp_path):
    root = tmp_path / "offsite"
    settings.BASEROW_DATA_DESTINATIONS = parse_data_destinations_env(
        json.dumps(
            [
                {
                    "name": "offsite",
                    "type": "filesystem",
                    "root": str(root),
                    "purposes": ["backup"],
                    "allow_trust_public_key": True,
                }
            ]
        )
    )
    return root


def _backup(data_fixture, user, name="Sales"):
    workspace = data_fixture.create_workspace(user=user)
    data_fixture.create_database_application(workspace=workspace, name=name)
    job = BackupHandler().start_backup(
        user, workspace.id, destination="offsite", sync=True
    )
    assert job.state == JOB_FINISHED, job.error
    return workspace, job


@pytest.mark.import_export_workspace
@pytest.mark.django_db(transaction=True)
def test_backup_is_uploaded_with_a_sidecar(
    data_fixture, backup_destination, use_tmp_media_root
):
    user = data_fixture.create_user()
    workspace, job = _backup(data_fixture, user)

    assert job.remote_key.startswith(f"backups/workspace={workspace.id}/")
    archive = backup_destination / job.remote_key
    sidecar = json.loads((backup_destination / f"{job.remote_key}.json").read_text())

    assert sidecar["sha256"] == hashlib.sha256(archive.read_bytes()).hexdigest()
    assert sidecar["workspace"] == {"id": workspace.id, "name": workspace.name}
    assert [application["name"] for application in sidecar["applications"]] == ["Sales"]
    assert sidecar["public_key_pem"]
    assert sidecar["instance_id"] == CoreHandler().get_settings().instance_id

    backups = BackupDestinationHandler().list_remote_backups(
        user, workspace.id, "offsite"
    )
    assert [backup["key"] for backup in backups] == [job.remote_key]


@pytest.mark.import_export_workspace
@pytest.mark.django_db(transaction=True)
def test_remote_backup_is_restored_into_another_workspace(
    data_fixture, backup_destination, use_tmp_media_root
):
    user = data_fixture.create_user()
    _, job = _backup(data_fixture, user)
    target = data_fixture.create_workspace(user=user)

    import_job = BackupDestinationHandler().restore_remote_backup(
        user, target.id, "offsite", job.remote_key, sync=True
    )

    assert import_job.state == JOB_FINISHED, import_job.error
    assert Application.objects.filter(workspace=target, name="Sales").exists()


@pytest.mark.import_export_workspace
@pytest.mark.django_db(transaction=True)
def test_backup_of_another_instance_needs_its_key_to_be_trusted(
    data_fixture, backup_destination, use_tmp_media_root
):
    member = data_fixture.create_user()
    staff = data_fixture.create_user(is_staff=True)
    _, job = _backup(data_fixture, staff)
    target = data_fixture.create_workspace(members=[member, staff])

    # Pretend the backup was made elsewhere: this instance no longer knows the key.
    ImportExportTrustedSource.objects.all().delete()
    settings = CoreHandler().get_settings()
    settings.verify_import_signature = True
    settings.save()

    handler = BackupDestinationHandler()

    with pytest.raises(ImportExportResourceUntrustedSignature):
        handler.restore_remote_backup(
            staff, target.id, "offsite", job.remote_key, sync=True
        )

    with pytest.raises(RemoteBackupTrustNotAllowed):
        handler.restore_remote_backup(
            member, target.id, "offsite", job.remote_key, trust_public_key=True
        )

    import_job = handler.restore_remote_backup(
        staff, target.id, "offsite", job.remote_key, trust_public_key=True, sync=True
    )

    assert import_job.state == JOB_FINISHED, import_job.error
    assert ImportExportTrustedSource.objects.filter(
        name__startswith="destination:offsite:"
    ).exists()


@pytest.mark.import_export_workspace
@pytest.mark.django_db(transaction=True)
def test_tampered_remote_backup_is_refused(
    data_fixture, backup_destination, use_tmp_media_root
):
    user = data_fixture.create_user()
    workspace, job = _backup(data_fixture, user)
    archive = backup_destination / job.remote_key
    archive.write_bytes(archive.read_bytes() + b"tampered")

    with pytest.raises(RemoteBackupCorrupted):
        BackupDestinationHandler().restore_remote_backup(
            user, workspace.id, "offsite", job.remote_key
        )


@pytest.mark.django_db
@pytest.mark.parametrize(
    "key",
    [
        "backups/../../etc/passwd.zip",
        "elsewhere/archive.zip",
        "backups/a.json",
        "backups/archive.zip",
        "backups/workspace=x/archive.zip",
        "backups/workspace=1/nested/archive.zip",
    ],
)
def test_restore_only_accepts_backup_archive_keys(
    data_fixture, backup_destination, key
):
    user = data_fixture.create_user()
    workspace = data_fixture.create_workspace(user=user)

    with pytest.raises(InvalidDataDestinationKey):
        BackupDestinationHandler().restore_remote_backup(
            user, workspace.id, "offsite", key
        )


@pytest.mark.import_export_workspace
@pytest.mark.django_db(transaction=True)
def test_restore_requires_access_to_the_backed_up_workspace(
    data_fixture, backup_destination, use_tmp_media_root
):
    owner = data_fixture.create_user()
    _, job = _backup(data_fixture, owner)
    outsider = data_fixture.create_user()
    target = data_fixture.create_workspace(user=outsider)

    with pytest.raises(RemoteBackupRestoreNotAllowed):
        BackupDestinationHandler().restore_remote_backup(
            outsider, target.id, "offsite", job.remote_key, sync=True
        )
    assert not Application.objects.filter(workspace=target).exists()

    staff = data_fixture.create_user(is_staff=True)
    staff_target = data_fixture.create_workspace(user=staff)
    import_job = BackupDestinationHandler().restore_remote_backup(
        staff, staff_target.id, "offsite", job.remote_key, sync=True
    )
    assert import_job.state == JOB_FINISHED, import_job.error


@pytest.mark.import_export_workspace
@pytest.mark.django_db(transaction=True)
def test_only_staff_can_restore_a_backup_of_another_instance(
    data_fixture, backup_destination, use_tmp_media_root
):
    user = data_fixture.create_user()
    workspace, job = _backup(data_fixture, user)
    sidecar_path = backup_destination / f"{job.remote_key}.json"
    sidecar = json.loads(sidecar_path.read_text())
    sidecar["instance_id"] = "another-instance"
    sidecar_path.write_text(json.dumps(sidecar))

    with pytest.raises(RemoteBackupRestoreNotAllowed):
        BackupDestinationHandler().restore_remote_backup(
            user, workspace.id, "offsite", job.remote_key, sync=True
        )


@pytest.mark.import_export_workspace
@pytest.mark.django_db(transaction=True)
def test_remote_retention_ignores_backups_of_another_instance(
    data_fixture,
    backup_destination,
    django_capture_on_commit_callbacks,
    use_tmp_media_root,
):
    user = data_fixture.create_user()
    workspace = data_fixture.create_workspace(user=user)
    data_fixture.create_database_application(workspace=workspace)
    schedule = data_fixture.create_backup_schedule(
        user=user, workspace=workspace, destination="offsite", keep_last=1
    )
    handler = BackupScheduleHandler()
    destination_handler = BackupDestinationHandler()

    # Another instance sharing the destination, with the same workspace and schedule
    # ids, already uploaded a backup.
    with django_capture_on_commit_callbacks(execute=True):
        handler.run_schedule(schedule)
    [foreign] = destination_handler.list_backups("offsite", workspace.id)
    sidecar_path = backup_destination / f"{foreign['key']}.json"
    sidecar = json.loads(sidecar_path.read_text())
    sidecar["instance_id"] = "another-instance"
    sidecar_path.write_text(json.dumps(sidecar))

    for _ in range(2):
        with django_capture_on_commit_callbacks(execute=True):
            handler.run_schedule(schedule)

    assert destination_handler.apply_remote_retention(schedule) == 1

    remaining = {
        backup["key"]
        for backup in destination_handler.list_backups("offsite", workspace.id)
    }
    assert foreign["key"] in remaining
    assert len(remaining) == 2


@pytest.mark.import_export_workspace
@pytest.mark.django_db(transaction=True)
def test_remote_retention_keeps_the_newest_backups_of_the_schedule(
    data_fixture,
    backup_destination,
    django_capture_on_commit_callbacks,
    use_tmp_media_root,
):
    user = data_fixture.create_user()
    workspace = data_fixture.create_workspace(user=user)
    data_fixture.create_database_application(workspace=workspace)
    schedule = data_fixture.create_backup_schedule(
        user=user, workspace=workspace, destination="offsite", keep_last=1
    )
    handler = BackupScheduleHandler()

    for _ in range(2):
        with django_capture_on_commit_callbacks(execute=True):
            handler.run_schedule(schedule)

    destination_handler = BackupDestinationHandler()
    backups = destination_handler.list_backups("offsite", workspace.id)
    assert len(backups) == 2
    assert {backup["schedule_id"] for backup in backups} == {schedule.id}

    assert destination_handler.apply_remote_retention(schedule) == 1

    remaining = destination_handler.list_backups("offsite", workspace.id)
    assert [backup["key"] for backup in remaining] == [backups[0]["key"]]
    assert not (backup_destination / backups[1]["key"]).exists()


@pytest.mark.import_export_workspace
@pytest.mark.django_db(transaction=True)
def test_list_remote_backups_endpoint(
    api_client, data_fixture, backup_destination, use_tmp_media_root
):
    user, token = data_fixture.create_user_and_token()
    workspace, job = _backup(data_fixture, user)

    response = api_client.get(
        reverse(
            "api:backups:remote_list",
            kwargs={"destination": "offsite", "workspace_id": workspace.id},
        ),
        HTTP_AUTHORIZATION=f"JWT {token}",
    )

    assert response.status_code == HTTP_200_OK
    [backup] = response.json()["results"]
    assert backup["key"] == job.remote_key
    assert backup["applications"][0]["name"] == "Sales"

    response = api_client.get(
        reverse(
            "api:backups:remote_list",
            kwargs={"destination": "missing", "workspace_id": workspace.id},
        ),
        HTTP_AUTHORIZATION=f"JWT {token}",
    )

    assert response.status_code == HTTP_404_NOT_FOUND
    assert response.json()["error"] == "ERROR_DATA_DESTINATION_DOES_NOT_EXIST"


@pytest.mark.import_export_workspace
@pytest.mark.django_db(transaction=True)
def test_backup_and_restore_management_commands(
    data_fixture, backup_destination, use_tmp_media_root, capsys
):
    user = data_fixture.create_user()
    workspace = data_fixture.create_workspace(user=user)
    data_fixture.create_database_application(workspace=workspace, name="Stock")
    target = data_fixture.create_workspace(user=user)

    call_command(
        "backup_to_destination",
        str(workspace.id),
        "--destination",
        "offsite",
        "--user-email",
        user.email,
    )
    call_command(
        "list_destination_backups",
        "--destination",
        "offsite",
        "--workspace-id",
        str(workspace.id),
    )
    listed = [
        json.loads(line)
        for line in capsys.readouterr().out.splitlines()
        if line.startswith("{")
    ]
    assert len(listed) == 1

    call_command(
        "restore_from_destination",
        "--destination",
        "offsite",
        "--key",
        listed[0]["key"],
        "--workspace-id",
        str(target.id),
        "--user-email",
        user.email,
    )

    assert Application.objects.filter(workspace=target, name="Stock").exists()


def _archive_and_sidecar_keys(destination_root):
    files = sorted(
        str(path.relative_to(destination_root))
        for path in destination_root.rglob("*")
        if path.is_file()
    )
    return files


@pytest.mark.import_export_workspace
@pytest.mark.django_db(transaction=True)
def test_archive_is_deleted_when_its_sidecar_cannot_be_written(
    data_fixture, backup_destination, use_tmp_media_root
):
    user = data_fixture.create_user()
    workspace = data_fixture.create_workspace(user=user)
    data_fixture.create_database_application(workspace=workspace)

    with (
        patch.object(
            DataDestinationHandler, "write_json", side_effect=OSError("disk full")
        ),
        pytest.raises(OSError, match="disk full"),
    ):
        BackupHandler().start_backup(
            user, workspace.id, destination="offsite", sync=True
        )

    assert _archive_and_sidecar_keys(backup_destination) == []


@pytest.mark.import_export_workspace
@pytest.mark.django_db(transaction=True)
def test_remote_retention_sweeps_only_old_orphan_archives(
    data_fixture,
    backup_destination,
    django_capture_on_commit_callbacks,
    use_tmp_media_root,
):
    user = data_fixture.create_user()
    workspace = data_fixture.create_workspace(user=user)
    data_fixture.create_database_application(workspace=workspace)
    schedule = data_fixture.create_backup_schedule(
        user=user, workspace=workspace, destination="offsite"
    )
    with django_capture_on_commit_callbacks(execute=True):
        BackupScheduleHandler().run_schedule(schedule)

    directory = backup_destination / f"backups/workspace={workspace.id}"
    old = directory / "20200101T000000Z_old.zip"
    fresh = directory / "20990101T000000Z_fresh.zip"
    for orphan in (old, fresh):
        orphan.write_bytes(b"partial")
    two_days_ago = time.time() - 2 * 24 * 3600
    os.utime(old, (two_days_ago, two_days_ago))

    # No keep_last / keep_days, the sweep still runs.
    assert BackupDestinationHandler().apply_remote_retention(schedule) == 0

    assert not old.exists()
    assert fresh.exists()
    [backup] = BackupDestinationHandler().list_backups("offsite", workspace.id)
    assert (backup_destination / backup["key"]).exists()


@pytest.mark.import_export_workspace
@pytest.mark.django_db(transaction=True)
def test_malformed_sidecars_are_skipped(
    data_fixture, backup_destination, use_tmp_media_root
):
    user = data_fixture.create_user()
    workspace, job = _backup(data_fixture, user)
    directory = backup_destination / f"backups/workspace={workspace.id}"
    (directory / "a.zip").write_bytes(b"zip")
    (directory / "a.zip.json").write_text("[]")
    (directory / "b.zip.json").write_text('"x"')
    (directory / "c.zip.json").write_text(json.dumps({"created_on": 5}))
    schedule = data_fixture.create_backup_schedule(
        user=user, workspace=workspace, destination="offsite", keep_days=1
    )

    handler = BackupDestinationHandler()
    keys = {backup["key"] for backup in handler.list_backups("offsite", workspace.id)}
    assert keys == {
        job.remote_key,
        f"{directory.relative_to(backup_destination)}/c.zip",
    }
    assert handler.apply_remote_retention(schedule) == 0

    with pytest.raises(RemoteBackupCorrupted):
        handler.restore_remote_backup(
            user,
            workspace.id,
            "offsite",
            f"backups/workspace={workspace.id}/a.zip",
        )


@pytest.mark.import_export_workspace
@pytest.mark.django_db(transaction=True)
def test_listing_endpoint_tolerates_sidecars_with_missing_fields(
    api_client, data_fixture, backup_destination, use_tmp_media_root
):
    user, token = data_fixture.create_user_and_token(is_staff=True)
    workspace = data_fixture.create_workspace(user=user)
    directory = backup_destination / f"backups/workspace={workspace.id}"
    directory.mkdir(parents=True)
    (directory / "x.zip.json").write_text("{}")

    response = api_client.get(
        reverse(
            "api:backups:remote_list",
            kwargs={"destination": "offsite", "workspace_id": workspace.id},
        ),
        HTTP_AUTHORIZATION=f"JWT {token}",
    )

    assert response.status_code == HTTP_200_OK
    [backup] = response.json()["results"]
    assert backup["key"] == f"backups/workspace={workspace.id}/x.zip"
    assert backup["size"] is None
    assert backup["sha256"] is None
    assert backup["created_on"] is None
    assert backup["only_structure"] is False
    assert backup["workspace"] == {}
    assert backup["applications"] == []


@pytest.mark.import_export_workspace
@pytest.mark.django_db(transaction=True)
def test_restore_is_refused_at_the_job_cap_before_downloading(
    data_fixture, backup_destination, use_tmp_media_root
):
    user = data_fixture.create_user()
    _, job = _backup(data_fixture, user)
    target = data_fixture.create_workspace(user=user)
    resource = data_fixture.create_import_export_resource(created_by=user)
    ImportApplicationsJob.objects.create(
        user=user, workspace=target, resource=resource, application_ids=[]
    )
    resources_before = ImportExportResource.objects.count()

    with (
        patch("baserow.core.backups.destination.SpooledTemporaryFile") as spooled,
        pytest.raises(MaxJobCountExceeded),
    ):
        BackupDestinationHandler().restore_remote_backup(
            user, target.id, "offsite", job.remote_key
        )

    spooled.assert_not_called()
    assert ImportExportResource.objects.count() == resources_before


@pytest.mark.import_export_workspace
@pytest.mark.django_db(transaction=True)
def test_failed_job_start_discards_the_resource_and_the_trusted_key(
    data_fixture, backup_destination, use_tmp_media_root
):
    staff = data_fixture.create_user(is_staff=True)
    _, job = _backup(data_fixture, staff)
    target = data_fixture.create_workspace(user=staff)
    ImportExportTrustedSource.objects.all().delete()
    resources_before = ImportExportResource.objects.count()
    import_dir = os.path.join(settings.MEDIA_ROOT, settings.IMPORT_FILES_DIRECTORY)

    with (
        patch.object(
            JobHandler, "create_and_start_job", side_effect=RuntimeError("boom")
        ),
        pytest.raises(RuntimeError),
    ):
        BackupDestinationHandler().restore_remote_backup(
            staff, target.id, "offsite", job.remote_key, trust_public_key=True
        )

    assert ImportExportResource.objects.count() == resources_before
    assert not ImportExportTrustedSource.objects.filter(
        name__startswith="destination:"
    ).exists()
    assert not os.path.isdir(import_dir) or os.listdir(import_dir) == []


@pytest.mark.import_export_workspace
@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize(
    "url_name", ["api:backups:remote_restore", "api:admin:backups:remote_restore"]
)
def test_remote_restore_downloads_outside_a_transaction(
    url_name, api_client, data_fixture, backup_destination, use_tmp_media_root
):
    user, token = data_fixture.create_user_and_token(is_staff=True)
    _, job = _backup(data_fixture, user)
    target = data_fixture.create_workspace(user=user)
    in_atomic = []
    original = ImportExportHandler.create_resource_from_file

    def spy(self, *args, **kwargs):
        in_atomic.append(connection.in_atomic_block)
        return original(self, *args, **kwargs)

    with patch.object(ImportExportHandler, "create_resource_from_file", spy):
        response = api_client.post(
            reverse(
                url_name,
                kwargs={"destination": "offsite", "workspace_id": target.id},
            ),
            {"key": job.remote_key},
            format="json",
            HTTP_AUTHORIZATION=f"JWT {token}",
        )

    assert response.status_code == HTTP_202_ACCEPTED, response.json()
    assert in_atomic == [False]


@pytest.mark.import_export_workspace
@pytest.mark.django_db(transaction=True)
def test_remote_key_excludes_the_prefix_and_fits_its_column(
    data_fixture, settings, tmp_path, use_tmp_media_root
):
    prefix = "/".join(["segment" * 4] * 17)
    assert len(prefix) >= 470
    settings.BASEROW_DATA_DESTINATIONS = parse_data_destinations_env(
        json.dumps(
            [
                {
                    "name": "offsite",
                    "type": "filesystem",
                    "root": str(tmp_path),
                    "prefix": prefix,
                    "purposes": ["backup"],
                }
            ]
        )
    )
    user = data_fixture.create_user()
    _, job = _backup(data_fixture, user)

    max_length = ExportApplicationsToDestinationJob._meta.get_field(
        "remote_key"
    ).max_length
    assert not job.remote_key.startswith(prefix)
    assert len(job.remote_key) <= max_length

    long_key = BackupDestinationHandler().get_archive_key(
        10**18 + 1, timezone.now(), uuid.uuid4()
    )
    assert len(long_key) <= max_length
