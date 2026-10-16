import json

from django.urls import reverse

import pytest
from rest_framework.status import HTTP_200_OK

from baserow.core.backups.handler import BackupHandler
from baserow.core.data_destinations.config import parse_data_destinations_env


@pytest.mark.import_export_workspace
@pytest.mark.django_db(transaction=True)
def test_listed_backups_expose_resource_and_destination(
    api_client, data_fixture, settings, tmp_path, use_tmp_media_root
):
    settings.BASEROW_DATA_DESTINATIONS = parse_data_destinations_env(
        json.dumps(
            [{"name": "offsite", "type": "filesystem", "root": str(tmp_path / "o")}]
        )
    )
    user, token = data_fixture.create_user_and_token()
    workspace = data_fixture.create_workspace(user=user)
    data_fixture.create_database_application(workspace=workspace)

    local = BackupHandler().start_backup(user, workspace.id, sync=True)
    remote = BackupHandler().start_backup(
        user, workspace.id, destination="offsite", sync=True
    )

    response = api_client.get(
        reverse("api:backups:list", kwargs={"workspace_id": workspace.id}),
        HTTP_AUTHORIZATION=f"JWT {token}",
    )

    assert response.status_code == HTTP_200_OK
    by_resource = {
        backup["resource_id"]: backup for backup in response.json()["results"]
    }
    assert by_resource[local.resource_id]["destination"] == ""
    assert by_resource[local.resource_id]["remote_key"] == ""
    assert by_resource[remote.resource_id]["destination"] == "offsite"
    assert by_resource[remote.resource_id]["remote_key"] == remote.remote_key
