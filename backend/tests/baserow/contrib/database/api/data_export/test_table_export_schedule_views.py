import json

from django.urls import reverse

import pytest
from rest_framework.status import (
    HTTP_200_OK,
    HTTP_202_ACCEPTED,
    HTTP_204_NO_CONTENT,
    HTTP_400_BAD_REQUEST,
    HTTP_404_NOT_FOUND,
)

from baserow.contrib.database.data_export.models import (
    TableExportRun,
    TableExportSchedule,
    TableExportState,
)
from baserow.core.data_destinations.config import parse_data_destinations_env

URL_PREFIX = "api:database:data_export"


@pytest.fixture
def lake(settings, tmp_path):
    settings.BASEROW_DATA_DESTINATIONS = parse_data_destinations_env(
        json.dumps(
            [
                {
                    "name": "lake",
                    "type": "filesystem",
                    "root": str(tmp_path / "lake"),
                    "purposes": ["datalake"],
                },
                {
                    "name": "vault",
                    "type": "filesystem",
                    "root": str(tmp_path / "vault"),
                    "purposes": ["backup"],
                },
            ]
        )
    )


def _create(api_client, token, workspace, database, **overrides):
    return api_client.post(
        reverse(f"{URL_PREFIX}:schedule_list", kwargs={"workspace_id": workspace.id}),
        {
            "database_id": database.id,
            "name": "Hourly",
            "cron": "0 * * * *",
            "destination": "lake",
            **overrides,
        },
        format="json",
        HTTP_AUTHORIZATION=f"JWT {token}",
    )


@pytest.mark.django_db
def test_create_list_update_and_delete_a_schedule(api_client, data_fixture, lake):
    user, token = data_fixture.create_user_and_token()
    workspace = data_fixture.create_workspace(user=user)
    database = data_fixture.create_database_application(workspace=workspace)
    table = data_fixture.create_database_table(database=database)

    response = _create(api_client, token, workspace, database, table_ids=[table.id])

    assert response.status_code == HTTP_200_OK, response.json()
    created = response.json()
    assert created["table_ids"] == [table.id]
    assert created["user_id"] == user.id
    assert "last_run_on" in created
    assert created["column_naming"] == "field_id"
    assert created["next_run_on"] is not None
    assert created["warnings"] == []

    response = api_client.get(
        reverse(f"{URL_PREFIX}:schedule_list", kwargs={"workspace_id": workspace.id}),
        HTTP_AUTHORIZATION=f"JWT {token}",
    )
    assert [schedule["id"] for schedule in response.json()] == [created["id"]]

    item_url = reverse(
        f"{URL_PREFIX}:schedule_item", kwargs={"schedule_id": created["id"]}
    )
    response = api_client.patch(
        item_url,
        {"cron": "0 0 1 * *"},
        format="json",
        HTTP_AUTHORIZATION=f"JWT {token}",
    )
    assert response.status_code == HTTP_200_OK
    # Monthly runs are further apart than the trash retention.
    assert response.json()["warnings"]

    response = api_client.delete(item_url, HTTP_AUTHORIZATION=f"JWT {token}")
    assert response.status_code == HTTP_204_NO_CONTENT
    assert not TableExportSchedule.objects.exists()


@pytest.mark.django_db
def test_create_schedule_is_validated(api_client, data_fixture, lake):
    user, token = data_fixture.create_user_and_token()
    workspace = data_fixture.create_workspace(user=user)
    database = data_fixture.create_database_application(workspace=workspace)
    other_table = data_fixture.create_database_table(user=user)

    response = _create(api_client, token, workspace, database, destination="missing")
    assert response.status_code == HTTP_404_NOT_FOUND
    assert response.json()["error"] == "ERROR_DATA_DESTINATION_DOES_NOT_EXIST"

    response = _create(api_client, token, workspace, database, destination="vault")
    assert response.status_code == HTTP_400_BAD_REQUEST
    assert response.json()["error"] == "ERROR_DATA_DESTINATION_PURPOSE_NOT_ALLOWED"

    response = _create(
        api_client, token, workspace, database, table_ids=[other_table.id]
    )
    assert response.status_code == HTTP_400_BAD_REQUEST
    assert response.json()["error"] == "ERROR_TABLE_EXPORT_TABLES_NOT_IN_DATABASE"

    response = _create(api_client, token, workspace, database, cron="whenever")
    assert response.status_code == HTTP_400_BAD_REQUEST
    assert response.json()["error"] == "ERROR_INVALID_TABLE_EXPORT_SCHEDULE_CRON"


@pytest.mark.django_db
def test_schedule_of_another_workspace_is_not_readable(api_client, data_fixture, lake):
    owner, owner_token = data_fixture.create_user_and_token()
    _, outsider_token = data_fixture.create_user_and_token()
    workspace = data_fixture.create_workspace(user=owner)
    database = data_fixture.create_database_application(workspace=workspace)
    schedule_id = _create(api_client, owner_token, workspace, database).json()["id"]

    response = api_client.get(
        reverse(f"{URL_PREFIX}:schedule_item", kwargs={"schedule_id": schedule_id}),
        HTTP_AUTHORIZATION=f"JWT {outsider_token}",
    )

    assert response.status_code == HTTP_400_BAD_REQUEST
    assert response.json()["error"] == "ERROR_USER_NOT_IN_GROUP"


@pytest.mark.django_db(transaction=True)
def test_run_now_lists_runs_and_resets_state(
    api_client, data_fixture, lake, django_capture_on_commit_callbacks
):
    user, token = data_fixture.create_user_and_token()
    workspace = data_fixture.create_workspace(user=user)
    database = data_fixture.create_database_application(workspace=workspace)
    table = data_fixture.create_database_table(database=database)
    data_fixture.create_text_field(table=table, name="Name", primary=True)
    schedule_id = _create(api_client, token, workspace, database).json()["id"]

    with django_capture_on_commit_callbacks(execute=True):
        response = api_client.post(
            reverse(f"{URL_PREFIX}:schedule_run", kwargs={"schedule_id": schedule_id}),
            {"mode": "full"},
            format="json",
            HTTP_AUTHORIZATION=f"JWT {token}",
        )

    assert response.status_code == HTTP_202_ACCEPTED
    assert TableExportRun.objects.filter(schedule_id=schedule_id).count() == 1

    response = api_client.get(
        reverse(f"{URL_PREFIX}:schedule_runs", kwargs={"schedule_id": schedule_id}),
        HTTP_AUTHORIZATION=f"JWT {token}",
    )
    [run] = response.json()
    assert run["table_id"] == table.id
    assert run["state"] == "finished"
    assert run["mode"] == "full"

    assert TableExportState.objects.filter(schedule_id=schedule_id).exists()
    response = api_client.post(
        reverse(
            f"{URL_PREFIX}:schedule_reset_state", kwargs={"schedule_id": schedule_id}
        ),
        HTTP_AUTHORIZATION=f"JWT {token}",
    )
    assert response.status_code == HTTP_204_NO_CONTENT
    assert not TableExportState.objects.filter(schedule_id=schedule_id).exists()
