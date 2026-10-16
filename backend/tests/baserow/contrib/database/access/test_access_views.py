from unittest.mock import patch

from django.shortcuts import reverse

import pytest
from rest_framework.status import (
    HTTP_200_OK,
    HTTP_400_BAD_REQUEST,
    HTTP_401_UNAUTHORIZED,
    HTTP_404_NOT_FOUND,
)

from baserow.contrib.database.access.models import DatabaseAccessGrant


def url(scope_type, scope_id):
    return reverse(
        "api:database:access:item",
        kwargs={"scope_type": scope_type, "scope_id": scope_id},
    )


def auth(data_fixture, user):
    return {"HTTP_AUTHORIZATION": f"JWT {data_fixture.generate_token(user)}"}


@pytest.mark.django_db
def test_admin_reads_scope_access(api_client, data_fixture, access_setup):
    s = access_setup
    team = s.team("Finance", s.member)
    s.grant("viewer", user=s.member, database=s.database)
    s.grant("none", team=team, table=s.table)

    response = api_client.get(url("table", s.table.id), **auth(data_fixture, s.admin))

    assert response.status_code == HTTP_200_OK, response.json()
    body = response.json()
    assert body["scope_type"] == "table"
    assert body["workspace_id"] == s.workspace.id
    subjects = {(x["subject_type"], x["subject_id"]): x for x in body["subjects"]}
    assert subjects[("team", team.id)]["level"] == "none"
    assert subjects[("user", s.member.id)]["level"] is None
    assert subjects[("user", s.member.id)]["inherited_level"] == "viewer"
    assert subjects[("user", s.member.id)]["inherited_from"] == "database"
    assert subjects[("user", s.admin.id)]["is_admin"] is True


@pytest.mark.django_db
@patch("baserow.ws.signals.broadcast_to_users")
def test_admin_sets_grants(
    mock_broadcast,
    api_client,
    data_fixture,
    access_setup,
    django_capture_on_commit_callbacks,
):
    s = access_setup

    with django_capture_on_commit_callbacks(execute=True):
        response = api_client.put(
            url("database", s.database.id),
            {
                "grants": [
                    {
                        "subject_type": "user",
                        "subject_id": s.member.id,
                        "level": "editor",
                    }
                ]
            },
            format="json",
            **auth(data_fixture, s.admin),
        )

    assert response.status_code == HTTP_200_OK, response.json()
    grant = DatabaseAccessGrant.objects.get()
    assert (grant.user_id, grant.database_id, grant.level) == (
        s.member.id,
        s.database.id,
        "editor",
    )
    mock_broadcast.delay.assert_called_once()
    user_ids, payload = mock_broadcast.delay.call_args.args
    assert user_ids == [s.member.id]
    assert payload == {"type": "permissions_updated", "workspace_id": s.workspace.id}


@pytest.mark.django_db
def test_member_cannot_manage_access(api_client, data_fixture, access_setup):
    s = access_setup

    response = api_client.put(
        url("workspace", s.workspace.id),
        {
            "grants": [
                {"subject_type": "user", "subject_id": s.member.id, "level": "builder"}
            ]
        },
        format="json",
        **auth(data_fixture, s.member),
    )

    assert response.status_code == HTTP_400_BAD_REQUEST
    assert response.json()["error"] == "ERROR_USER_INVALID_GROUP_PERMISSIONS"
    assert not DatabaseAccessGrant.objects.exists()


@pytest.mark.django_db
def test_admin_of_other_workspace_cannot_manage_access(
    api_client, data_fixture, access_setup
):
    s = access_setup
    stranger = data_fixture.create_user()
    data_fixture.create_workspace(user=stranger)

    response = api_client.get(url("table", s.table.id), **auth(data_fixture, stranger))

    assert response.status_code == HTTP_400_BAD_REQUEST
    assert response.json()["error"] == "ERROR_USER_NOT_IN_GROUP"


@pytest.mark.django_db
def test_staff_manages_any_workspace(api_client, data_fixture, access_setup):
    s = access_setup
    staff = data_fixture.create_user(is_staff=True)

    response = api_client.put(
        url("table", s.table.id),
        {
            "grants": [
                {"subject_type": "user", "subject_id": s.member.id, "level": "none"}
            ]
        },
        format="json",
        **auth(data_fixture, staff),
    )

    assert response.status_code == HTTP_200_OK, response.json()
    assert DatabaseAccessGrant.objects.filter(table=s.table, level="none").exists()


@pytest.mark.django_db
def test_invalid_scope_and_subject(api_client, data_fixture, access_setup):
    s = access_setup
    outsider = data_fixture.create_user()

    response = api_client.get(url("table", 0), **auth(data_fixture, s.admin))
    assert response.status_code == HTTP_404_NOT_FOUND
    assert response.json()["error"] == "ERROR_ACCESS_SCOPE_DOES_NOT_EXIST"

    response = api_client.put(
        url("table", s.table.id),
        {
            "grants": [
                {"subject_type": "user", "subject_id": outsider.id, "level": "none"}
            ]
        },
        format="json",
        **auth(data_fixture, s.admin),
    )
    assert response.status_code == HTTP_400_BAD_REQUEST
    assert response.json()["error"] == "ERROR_INVALID_ACCESS_SUBJECT"

    response = api_client.put(
        url("table", s.table.id),
        {
            "grants": [
                {"subject_type": "user", "subject_id": s.member.id, "level": "owner"}
            ]
        },
        format="json",
        **auth(data_fixture, s.admin),
    )
    assert response.status_code == HTTP_400_BAD_REQUEST
    assert response.json()["error"] == "ERROR_REQUEST_BODY_VALIDATION"


@pytest.mark.django_db
def test_restricted_member_only_sees_granted_tables_in_api(
    api_client, data_fixture, access_setup
):
    s = access_setup
    s.grant("none", user=s.member)
    s.grant("editor", user=s.member, table=s.table)
    member_auth = auth(data_fixture, s.member)

    response = api_client.get(
        reverse("api:applications:list", kwargs={"workspace_id": s.workspace.id}),
        **member_auth,
    )
    assert response.status_code == HTTP_200_OK, response.json()
    applications = {app["id"]: app for app in response.json()}
    assert set(applications) == {s.database.id}
    assert [t["id"] for t in applications[s.database.id]["tables"]] == [s.table.id]

    response = api_client.get(
        reverse("api:database:tables:item", kwargs={"table_id": s.other_table.id}),
        **member_auth,
    )
    assert response.status_code == HTTP_401_UNAUTHORIZED
    assert response.json()["error"] == "PERMISSION_DENIED"
