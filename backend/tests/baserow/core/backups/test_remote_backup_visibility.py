import json

import pytest

from baserow.core.backups.destination import BackupDestinationHandler
from baserow.core.backups.exceptions import RemoteBackupRestoreNotAllowed
from baserow.core.backups.handler import BackupHandler
from baserow.core.data_destinations.config import parse_data_destinations_env
from baserow.core.jobs.constants import JOB_FINISHED


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


def _shared_workspace(data_fixture):
    admin = data_fixture.create_user()
    member_one = data_fixture.create_user()
    member_two = data_fixture.create_user()
    workspace = data_fixture.create_workspace(
        user=admin, members=[member_one, member_two]
    )
    data_fixture.create_database_application(workspace=workspace, name="Sales")
    jobs = {}
    for name, user in (
        ("admin", admin),
        ("one", member_one),
        ("two", member_two),
    ):
        job = BackupHandler().start_backup(
            user, workspace.id, destination="offsite", sync=True
        )
        assert job.state == JOB_FINISHED, job.error
        jobs[name] = job
    return admin, member_one, member_two, workspace, jobs


def _keys(backups):
    return {backup["key"] for backup in backups}


@pytest.mark.import_export_workspace
@pytest.mark.django_db(transaction=True)
def test_members_list_only_their_own_remote_backups_and_admins_all(
    data_fixture, backup_destination, use_tmp_media_root
):
    admin, member_one, member_two, workspace, jobs = _shared_workspace(data_fixture)
    handler = BackupDestinationHandler()

    assert _keys(handler.list_remote_backups(member_one, workspace.id, "offsite")) == {
        jobs["one"].remote_key
    }
    assert _keys(handler.list_remote_backups(member_two, workspace.id, "offsite")) == {
        jobs["two"].remote_key
    }
    assert _keys(handler.list_remote_backups(admin, workspace.id, "offsite")) == {
        job.remote_key for job in jobs.values()
    }


@pytest.mark.import_export_workspace
@pytest.mark.django_db(transaction=True)
def test_sidecar_records_the_creator_id(
    data_fixture, backup_destination, use_tmp_media_root
):
    admin, _, _, _, jobs = _shared_workspace(data_fixture)

    sidecar = json.loads(
        (backup_destination / f"{jobs['admin'].remote_key}.json").read_text()
    )

    assert sidecar["created_by_id"] == admin.id
    assert sidecar["created_by"] == admin.email


@pytest.mark.import_export_workspace
@pytest.mark.django_db(transaction=True)
def test_old_sidecars_without_a_creator_id_match_on_email(
    data_fixture, backup_destination, use_tmp_media_root
):
    _, member_one, _, workspace, jobs = _shared_workspace(data_fixture)
    for job in jobs.values():
        path = backup_destination / f"{job.remote_key}.json"
        sidecar = json.loads(path.read_text())
        del sidecar["created_by_id"]
        path.write_text(json.dumps(sidecar))

    backups = BackupDestinationHandler().list_remote_backups(
        member_one, workspace.id, "offsite"
    )

    assert _keys(backups) == {jobs["one"].remote_key}


@pytest.mark.import_export_workspace
@pytest.mark.django_db(transaction=True)
def test_other_instance_backups_are_hidden_from_non_staff_but_not_staff(
    data_fixture, backup_destination, use_tmp_media_root
):
    admin, _, _, workspace, jobs = _shared_workspace(data_fixture)
    path = backup_destination / f"{jobs['one'].remote_key}.json"
    sidecar = json.loads(path.read_text())
    sidecar["instance_id"] = "another-instance"
    path.write_text(json.dumps(sidecar))
    staff = data_fixture.create_user(is_staff=True)
    handler = BackupDestinationHandler()

    assert _keys(handler.list_remote_backups(admin, workspace.id, "offsite")) == {
        jobs["admin"].remote_key,
        jobs["two"].remote_key,
    }
    # Staff are not a member of the workspace and still see every backup.
    assert _keys(handler.list_remote_backups(staff, workspace.id, "offsite")) == {
        job.remote_key for job in jobs.values()
    }


@pytest.mark.import_export_workspace
@pytest.mark.django_db(transaction=True)
def test_member_cannot_restore_the_backup_of_another_member(
    data_fixture, backup_destination, use_tmp_media_root
):
    admin, member_one, member_two, workspace, jobs = _shared_workspace(data_fixture)
    target = data_fixture.create_workspace(user=member_one)
    handler = BackupDestinationHandler()

    with pytest.raises(RemoteBackupRestoreNotAllowed):
        handler.restore_remote_backup(
            member_one, target.id, "offsite", jobs["two"].remote_key, sync=True
        )

    own = handler.restore_remote_backup(
        member_one, target.id, "offsite", jobs["one"].remote_key, sync=True
    )
    assert own.state == JOB_FINISHED, own.error

    admin_target = data_fixture.create_workspace(user=admin)
    restored = handler.restore_remote_backup(
        admin, admin_target.id, "offsite", jobs["two"].remote_key, sync=True
    )
    assert restored.state == JOB_FINISHED, restored.error
