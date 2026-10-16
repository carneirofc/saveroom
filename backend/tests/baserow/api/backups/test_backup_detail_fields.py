import json

from django.urls import reverse

import pytest
from rest_framework.status import HTTP_200_OK

from baserow.core.backups.handler import BackupHandler
from baserow.core.data_destinations.config import parse_data_destinations_env
from baserow.core.jobs.constants import JOB_FINISHED


@pytest.fixture
def offsite(settings, tmp_path):
    settings.BASEROW_DATA_DESTINATIONS = parse_data_destinations_env(
        json.dumps(
            [
                {
                    "name": "offsite",
                    "type": "filesystem",
                    "root": str(tmp_path / "offsite"),
                    "purposes": ["backup"],
                    "allow_trust_public_key": True,
                },
                {
                    "name": "plain",
                    "type": "filesystem",
                    "root": str(tmp_path / "plain"),
                },
            ]
        )
    )
    return tmp_path / "offsite"


@pytest.mark.import_export_workspace
@pytest.mark.django_db(transaction=True)
def test_remote_backups_expose_creator_and_instance(
    api_client, data_fixture, offsite, use_tmp_media_root
):
    user, token = data_fixture.create_user_and_token(is_staff=True)
    workspace = data_fixture.create_workspace(user=user)
    data_fixture.create_database_application(workspace=workspace)
    job = BackupHandler().start_backup(
        user, workspace.id, destination="offsite", sync=True
    )
    assert job.state == JOB_FINISHED, job.error

    # A sidecar of another instance and one without a creator.
    directory = offsite / f"backups/workspace={workspace.id}"
    (directory / "foreign.zip.json").write_text(
        json.dumps({"instance_id": "another-instance"})
    )

    url = reverse(
        "api:backups:remote_list",
        kwargs={"destination": "offsite", "workspace_id": workspace.id},
    )
    response = api_client.get(url, HTTP_AUTHORIZATION=f"JWT {token}")

    assert response.status_code == HTTP_200_OK
    by_key = {backup["key"]: backup for backup in response.json()["results"]}
    own = by_key[job.remote_key]
    assert own["created_by"] == user.email
    assert own["is_this_instance"] is True
    foreign = by_key[f"backups/workspace={workspace.id}/foreign.zip"]
    assert foreign["created_by"] is None
    assert foreign["is_this_instance"] is False


@pytest.mark.django_db
def test_data_destinations_expose_allow_trust_public_key(
    api_client, data_fixture, offsite
):
    _, token = data_fixture.create_user_and_token()

    response = api_client.get(
        reverse("api:data_destinations:list"), HTTP_AUTHORIZATION=f"JWT {token}"
    )

    assert response.status_code == HTTP_200_OK
    by_name = {item["name"]: item for item in response.json()}
    assert by_name["offsite"]["allow_trust_public_key"] is True
    assert by_name["plain"]["allow_trust_public_key"] is False


@pytest.mark.django_db
def test_backup_schedule_exposes_owner_and_last_run(api_client, data_fixture):
    user, token = data_fixture.create_user_and_token()
    workspace = data_fixture.create_workspace(user=user)
    schedule = data_fixture.create_backup_schedule(user=user, workspace=workspace)

    response = api_client.get(
        reverse("api:backups:schedule_list", kwargs={"workspace_id": workspace.id}),
        HTTP_AUTHORIZATION=f"JWT {token}",
    )

    assert response.status_code == HTTP_200_OK
    [item] = response.json()
    assert item["id"] == schedule.id
    assert item["user_id"] == user.id
    assert "last_run_on" in item
