import json

from django.urls import reverse

import pytest
from rest_framework.status import (
    HTTP_200_OK,
    HTTP_400_BAD_REQUEST,
    HTTP_403_FORBIDDEN,
    HTTP_404_NOT_FOUND,
    HTTP_413_REQUEST_ENTITY_TOO_LARGE,
)


def _json(response):
    return json.loads(b"".join(response.streaming_content))


@pytest.fixture
def workspace_with_a_row(data_fixture):
    user = data_fixture.create_user()
    workspace = data_fixture.create_workspace(user=user)
    database = data_fixture.create_database_application(
        workspace=workspace, name="Company"
    )
    table = data_fixture.create_database_table(database=database, name="People")
    field = data_fixture.create_text_field(table=table, name="Name")
    table.get_model().objects.create(**{f"field_{field.id}": "Ada"})
    return user, workspace, database, table, field


@pytest.mark.django_db
def test_get_workspace_contents(api_client, data_fixture, workspace_with_a_row):
    user, workspace, database, table, field = workspace_with_a_row
    token = data_fixture.generate_token(user)

    response = api_client.get(
        reverse("api:contents:workspace", kwargs={"workspace_id": workspace.id}),
        HTTP_AUTHORIZATION=f"JWT {token}",
    )

    assert response.status_code == HTTP_200_OK
    contents = _json(response)

    assert contents["id"] == workspace.id
    assert contents["exclude_data"] is False
    assert len(contents["applications"]) == 1

    application = contents["applications"][0]
    assert application["name"] == "Company"

    exported_table = application["tables"][0]
    assert exported_table["name"] == "People"
    assert [f["name"] for f in exported_table["fields"]] == ["Name"]
    assert [r[f"field_{field.id}"] for r in exported_table["rows"]] == ["Ada"]


@pytest.mark.django_db
def test_get_workspace_contents_excluding_data(
    api_client, data_fixture, workspace_with_a_row
):
    user, workspace, database, table, field = workspace_with_a_row
    token = data_fixture.generate_token(user)

    response = api_client.get(
        reverse("api:contents:workspace", kwargs={"workspace_id": workspace.id})
        + "?exclude_data=true",
        HTTP_AUTHORIZATION=f"JWT {token}",
    )

    assert response.status_code == HTTP_200_OK
    contents = _json(response)

    assert contents["exclude_data"] is True
    exported_table = contents["applications"][0]["tables"][0]
    # The structure is still there, the rows are not.
    assert [f["name"] for f in exported_table["fields"]] == ["Name"]
    assert exported_table["rows"] == []


@pytest.mark.django_db
def test_get_application_contents(api_client, data_fixture, workspace_with_a_row):
    user, workspace, database, table, field = workspace_with_a_row
    data_fixture.create_database_application(workspace=workspace, name="Other")
    token = data_fixture.generate_token(user)

    response = api_client.get(
        reverse("api:contents:application", kwargs={"application_id": database.id}),
        HTTP_AUTHORIZATION=f"JWT {token}",
    )

    assert response.status_code == HTTP_200_OK
    contents = _json(response)

    assert [a["name"] for a in contents["applications"]] == ["Company"]


@pytest.mark.django_db
def test_get_contents_of_workspace_the_user_is_not_in(api_client, data_fixture):
    _, token = data_fixture.create_user_and_token()
    workspace = data_fixture.create_workspace()

    response = api_client.get(
        reverse("api:contents:workspace", kwargs={"workspace_id": workspace.id}),
        HTTP_AUTHORIZATION=f"JWT {token}",
    )

    assert response.status_code == HTTP_400_BAD_REQUEST
    assert response.json()["error"] == "ERROR_USER_NOT_IN_GROUP"


@pytest.mark.django_db
def test_get_contents_of_missing_application(api_client, data_fixture):
    _, token = data_fixture.create_user_and_token()

    response = api_client.get(
        reverse("api:contents:application", kwargs={"application_id": 999999}),
        HTTP_AUTHORIZATION=f"JWT {token}",
    )

    assert response.status_code == HTTP_404_NOT_FOUND
    assert response.json()["error"] == "ERROR_APPLICATION_DOES_NOT_EXIST"


@pytest.mark.django_db
def test_contents_over_the_row_limit_are_refused(
    api_client, data_fixture, settings, workspace_with_a_row
):
    user, workspace, database, table, field = workspace_with_a_row
    settings.BASEROW_CONTENTS_API_MAX_ROWS = 1
    table.get_model().objects.create(**{f"field_{field.id}": "Grace"})

    token = data_fixture.generate_token(user)
    response = api_client.get(
        reverse("api:contents:workspace", kwargs={"workspace_id": workspace.id}),
        HTTP_AUTHORIZATION=f"JWT {token}",
    )

    assert response.status_code == HTTP_413_REQUEST_ENTITY_TOO_LARGE
    assert response.json()["error"] == "ERROR_CONTENTS_TOO_LARGE"


@pytest.mark.django_db
def test_row_limit_does_not_apply_when_excluding_data(
    api_client, data_fixture, settings, workspace_with_a_row
):
    user, workspace, database, table, field = workspace_with_a_row
    settings.BASEROW_CONTENTS_API_MAX_ROWS = 1
    table.get_model().objects.create(**{f"field_{field.id}": "Grace"})

    token = data_fixture.generate_token(user)
    response = api_client.get(
        reverse("api:contents:workspace", kwargs={"workspace_id": workspace.id})
        + "?exclude_data=true",
        HTTP_AUTHORIZATION=f"JWT {token}",
    )

    assert response.status_code == HTTP_200_OK


@pytest.mark.django_db
def test_contents_readable_with_an_api_client_key(
    api_client, data_fixture, workspace_with_a_row
):
    user, workspace, database, table, field = workspace_with_a_row
    _, raw_key = data_fixture.create_api_client_and_key(
        user=user, workspace=workspace, scopes=["contents.read"]
    )

    response = api_client.get(
        reverse("api:contents:workspace", kwargs={"workspace_id": workspace.id}),
        HTTP_AUTHORIZATION=f"Client {raw_key}",
    )

    assert response.status_code == HTTP_200_OK
    assert _json(response)["id"] == workspace.id


@pytest.mark.django_db
def test_contents_refused_without_the_scope(
    api_client, data_fixture, workspace_with_a_row
):
    user, workspace, database, table, field = workspace_with_a_row
    _, raw_key = data_fixture.create_api_client_and_key(
        user=user, workspace=workspace, scopes=["backup.read"]
    )

    response = api_client.get(
        reverse("api:contents:workspace", kwargs={"workspace_id": workspace.id}),
        HTTP_AUTHORIZATION=f"Client {raw_key}",
    )

    assert response.status_code == HTTP_403_FORBIDDEN
