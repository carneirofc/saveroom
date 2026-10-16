from django.urls import reverse

import pytest
from rest_framework.status import (
    HTTP_200_OK,
    HTTP_202_ACCEPTED,
    HTTP_403_FORBIDDEN,
)


@pytest.mark.django_db
def test_non_staff_cannot_list_admin_backup_schedules(api_client, data_fixture):
    _, token = data_fixture.create_user_and_token()
    workspace = data_fixture.create_workspace()

    response = api_client.get(
        reverse(
            "api:admin:backups:schedule_list", kwargs={"workspace_id": workspace.id}
        ),
        format="json",
        HTTP_AUTHORIZATION=f"JWT {token}",
    )

    assert response.status_code == HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_staff_can_list_backup_schedules_of_a_workspace_they_are_not_in(
    api_client, data_fixture
):
    staff_user, staff_token = data_fixture.create_user_and_token(is_staff=True)
    workspace = data_fixture.create_workspace()  # staff_user is not a member

    response = api_client.get(
        reverse(
            "api:admin:backups:schedule_list", kwargs={"workspace_id": workspace.id}
        ),
        format="json",
        HTTP_AUTHORIZATION=f"JWT {staff_token}",
    )

    assert response.status_code == HTTP_200_OK
    assert response.json() == []


@pytest.mark.django_db
def test_staff_can_create_backup_schedule_of_a_workspace_they_are_not_in(
    api_client, data_fixture
):
    staff_user, staff_token = data_fixture.create_user_and_token(is_staff=True)
    workspace = data_fixture.create_workspace()

    response = api_client.post(
        reverse(
            "api:admin:backups:schedule_list", kwargs={"workspace_id": workspace.id}
        ),
        {"name": "Nightly", "cron": "0 3 * * *"},
        format="json",
        HTTP_AUTHORIZATION=f"JWT {staff_token}",
    )

    assert response.status_code == HTTP_200_OK
    response_json = response.json()
    assert response_json["name"] == "Nightly"
    assert response_json["workspace"] == workspace.id


@pytest.mark.import_export_workspace
@pytest.mark.django_db(transaction=True)
def test_staff_can_backup_a_workspace_they_are_not_in(
    api_client,
    data_fixture,
    django_capture_on_commit_callbacks,
    use_tmp_media_root,
):
    staff_user, staff_token = data_fixture.create_user_and_token(is_staff=True)
    workspace = data_fixture.create_workspace()
    database = data_fixture.create_database_application(workspace=workspace)
    table = data_fixture.create_database_table(database=database)
    data_fixture.create_text_field(table=table, name="Name")

    with django_capture_on_commit_callbacks(execute=True):
        response = api_client.post(
            reverse("api:admin:backups:start", kwargs={"workspace_id": workspace.id}),
            {},
            format="json",
            HTTP_AUTHORIZATION=f"JWT {staff_token}",
        )

    assert response.status_code == HTTP_202_ACCEPTED

    response = api_client.get(
        reverse("api:admin:backups:list", kwargs={"workspace_id": workspace.id}),
        format="json",
        HTTP_AUTHORIZATION=f"JWT {staff_token}",
    )

    assert response.status_code == HTTP_200_OK
    results = response.json()["results"]
    assert len(results) == 1
    assert results[0]["url"] is not None


@pytest.mark.django_db
def test_regular_member_backups_api_is_unaffected(api_client, data_fixture):
    user, token = data_fixture.create_user_and_token()
    workspace = data_fixture.create_workspace(user=user)

    response = api_client.get(
        reverse("api:backups:list", kwargs={"workspace_id": workspace.id}),
        format="json",
        HTTP_AUTHORIZATION=f"JWT {token}",
    )

    assert response.status_code == HTTP_200_OK
