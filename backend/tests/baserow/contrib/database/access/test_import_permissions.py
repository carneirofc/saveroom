"""
An editor may import rows into a table, but not through an import mode that moves
the existing rows to the trash. That needs `database.table.replace_rows`, which no
level below `builder` lists.
"""

from django.shortcuts import reverse

import pytest
from rest_framework.status import HTTP_200_OK, HTTP_401_UNAUTHORIZED

from baserow.core.exceptions import PermissionDenied
from baserow.core.jobs.handler import JobHandler


def auth(data_fixture, user):
    return {"HTTP_AUTHORIZATION": f"JWT {data_fixture.generate_token(user)}"}


def import_url(table):
    return reverse("api:database:tables:import_async", kwargs={"table_id": table.id})


def preview_url(table):
    return reverse("api:database:tables:import_preview", kwargs={"table_id": table.id})


@pytest.fixture
def importable_table(data_fixture, access_setup):
    """
    A table of the access setup with a text field, so rows can be imported into it.
    """

    data_fixture.create_text_field(table=access_setup.table, user=access_setup.admin)
    return access_setup.table


INSERT_BODY = {"data": [["a"], ["b"]], "configuration": {"mode": "insert"}}
REPLACE_BODY = {"data": [["a"], ["b"]], "configuration": {"mode": "replace"}}


@pytest.mark.django_db
def test_editor_imports_rows(api_client, data_fixture, access_setup, importable_table):
    access_setup.grant("editor", user=access_setup.member, table=importable_table)

    response = api_client.post(
        import_url(importable_table),
        INSERT_BODY,
        format="json",
        **auth(data_fixture, access_setup.member),
    )

    assert response.status_code == HTTP_200_OK, response.json()
    assert response.json()["type"] == "file_import"


@pytest.mark.django_db
def test_editor_cannot_replace_rows(
    api_client, data_fixture, access_setup, importable_table
):
    access_setup.grant("editor", user=access_setup.member, table=importable_table)

    response = api_client.post(
        import_url(importable_table),
        REPLACE_BODY,
        format="json",
        **auth(data_fixture, access_setup.member),
    )

    assert response.status_code == HTTP_401_UNAUTHORIZED
    assert response.json()["error"] == "PERMISSION_DENIED"


@pytest.mark.django_db
def test_editor_cannot_delete_unmatched_rows(
    api_client, data_fixture, access_setup, importable_table
):
    access_setup.grant("editor", user=access_setup.member, table=importable_table)
    field = importable_table.field_set.get()

    response = api_client.post(
        import_url(importable_table),
        {
            "data": [["a"]],
            "configuration": {
                "mode": "upsert",
                "upsert_fields": [field.id],
                "upsert_values": [["a"]],
                "delete_unmatched": True,
            },
        },
        format="json",
        **auth(data_fixture, access_setup.member),
    )

    assert response.status_code == HTTP_401_UNAUTHORIZED
    assert response.json()["error"] == "PERMISSION_DENIED"


@pytest.mark.django_db
def test_builder_replaces_rows(
    api_client, data_fixture, access_setup, importable_table
):
    access_setup.grant("builder", user=access_setup.member, table=importable_table)

    response = api_client.post(
        import_url(importable_table),
        REPLACE_BODY,
        format="json",
        **auth(data_fixture, access_setup.member),
    )

    assert response.status_code == HTTP_200_OK, response.json()
    assert response.json()["type"] == "file_import"


@pytest.mark.django_db
def test_editor_cannot_preview_a_replace(
    api_client, data_fixture, access_setup, importable_table
):
    access_setup.grant("editor", user=access_setup.member, table=importable_table)

    allowed = api_client.post(
        preview_url(importable_table),
        INSERT_BODY,
        format="json",
        **auth(data_fixture, access_setup.member),
    )
    refused = api_client.post(
        preview_url(importable_table),
        REPLACE_BODY,
        format="json",
        **auth(data_fixture, access_setup.member),
    )

    assert allowed.status_code == HTTP_200_OK, allowed.json()
    assert refused.status_code == HTTP_401_UNAUTHORIZED
    assert refused.json()["error"] == "PERMISSION_DENIED"


@pytest.mark.django_db
def test_the_job_itself_refuses_a_destructive_import(
    data_fixture, access_setup, importable_table
):
    """
    The API view isn't the only caller of the job, so the job checks too.
    """

    access_setup.grant("editor", user=access_setup.member, table=importable_table)

    with pytest.raises(PermissionDenied):
        JobHandler().create_and_start_job(
            access_setup.member,
            "file_import",
            data=[["a"]],
            table=importable_table,
            database=importable_table.database,
            configuration={"mode": "replace"},
        )
