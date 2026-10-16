from django.urls import reverse

import pytest
from rest_framework.status import (
    HTTP_200_OK,
    HTTP_202_ACCEPTED,
    HTTP_204_NO_CONTENT,
    HTTP_400_BAD_REQUEST,
    HTTP_404_NOT_FOUND,
)

from baserow.core.models import ImportExportResource


@pytest.mark.import_export_workspace
@pytest.mark.django_db
def test_list_backups_of_missing_workspace(api_client, data_fixture):
    _, token = data_fixture.create_user_and_token()

    response = api_client.get(
        reverse("api:backups:list", kwargs={"workspace_id": 999999}),
        format="json",
        HTTP_AUTHORIZATION=f"JWT {token}",
    )

    assert response.status_code == HTTP_404_NOT_FOUND
    assert response.json()["error"] == "ERROR_GROUP_DOES_NOT_EXIST"


@pytest.mark.import_export_workspace
@pytest.mark.django_db
def test_start_backup_of_workspace_the_user_is_not_in(api_client, data_fixture):
    _, token = data_fixture.create_user_and_token()
    workspace = data_fixture.create_workspace()

    response = api_client.post(
        reverse("api:backups:start", kwargs={"workspace_id": workspace.id}),
        {},
        format="json",
        HTTP_AUTHORIZATION=f"JWT {token}",
    )

    assert response.status_code == HTTP_400_BAD_REQUEST
    assert response.json()["error"] == "ERROR_USER_NOT_IN_GROUP"


@pytest.mark.import_export_workspace
@pytest.mark.django_db(transaction=True)
def test_backup_whole_workspace(
    api_client,
    data_fixture,
    django_capture_on_commit_callbacks,
    use_tmp_media_root,
):
    user = data_fixture.create_user()
    workspace = data_fixture.create_workspace(user=user)
    database = data_fixture.create_database_application(workspace=workspace)
    table = data_fixture.create_database_table(database=database)
    data_fixture.create_text_field(table=table, name="Name")

    with django_capture_on_commit_callbacks(execute=True):
        token = data_fixture.generate_token(user)
        response = api_client.post(
            reverse("api:backups:start", kwargs={"workspace_id": workspace.id}),
            {},
            format="json",
            HTTP_AUTHORIZATION=f"JWT {token}",
        )

    assert response.status_code == HTTP_202_ACCEPTED
    assert response.json()["type"] == "export_applications"

    token = data_fixture.generate_token(user)
    response = api_client.get(
        reverse("api:backups:list", kwargs={"workspace_id": workspace.id}),
        format="json",
        HTTP_AUTHORIZATION=f"JWT {token}",
    )

    assert response.status_code == HTTP_200_OK
    results = response.json()["results"]
    assert len(results) == 1
    assert results[0]["exported_file_name"] is not None
    assert results[0]["url"] is not None


@pytest.mark.import_export_workspace
@pytest.mark.django_db(transaction=True)
def test_backup_a_single_application(
    api_client,
    data_fixture,
    django_capture_on_commit_callbacks,
    use_tmp_media_root,
):
    user = data_fixture.create_user()
    workspace = data_fixture.create_workspace(user=user)
    database = data_fixture.create_database_application(workspace=workspace)
    data_fixture.create_database_application(workspace=workspace)

    with django_capture_on_commit_callbacks(execute=True):
        token = data_fixture.generate_token(user)
        response = api_client.post(
            reverse("api:backups:start", kwargs={"workspace_id": workspace.id}),
            {"application_ids": [database.id]},
            format="json",
            HTTP_AUTHORIZATION=f"JWT {token}",
        )

    assert response.status_code == HTTP_202_ACCEPTED

    token = data_fixture.generate_token(user)
    response = api_client.get(
        reverse("api:jobs:item", kwargs={"job_id": response.json()["id"]}),
        format="json",
        HTTP_AUTHORIZATION=f"JWT {token}",
    )

    assert response.json()["state"] == "finished"


@pytest.mark.import_export_workspace
@pytest.mark.django_db(transaction=True)
def test_get_and_delete_a_backup(
    api_client,
    data_fixture,
    django_capture_on_commit_callbacks,
    use_tmp_media_root,
):
    user = data_fixture.create_user()
    workspace = data_fixture.create_workspace(user=user)
    data_fixture.create_database_application(workspace=workspace)

    with django_capture_on_commit_callbacks(execute=True):
        token = data_fixture.generate_token(user)
        api_client.post(
            reverse("api:backups:start", kwargs={"workspace_id": workspace.id}),
            {},
            format="json",
            HTTP_AUTHORIZATION=f"JWT {token}",
        )

    token = data_fixture.generate_token(user)
    listed = api_client.get(
        reverse("api:backups:list", kwargs={"workspace_id": workspace.id}),
        format="json",
        HTTP_AUTHORIZATION=f"JWT {token}",
    ).json()["results"]
    resource_id = ImportExportResource.objects.get().id

    response = api_client.get(
        reverse(
            "api:backups:item",
            kwargs={"workspace_id": workspace.id, "resource_id": resource_id},
        ),
        format="json",
        HTTP_AUTHORIZATION=f"JWT {token}",
    )
    assert response.status_code == HTTP_200_OK
    assert response.json()["id"] == listed[0]["id"]

    response = api_client.delete(
        reverse(
            "api:backups:item",
            kwargs={"workspace_id": workspace.id, "resource_id": resource_id},
        ),
        format="json",
        HTTP_AUTHORIZATION=f"JWT {token}",
    )
    assert response.status_code == HTTP_204_NO_CONTENT

    resource = ImportExportResource.objects_and_trash.get(id=resource_id)
    assert resource.marked_for_deletion is True


@pytest.mark.import_export_workspace
@pytest.mark.django_db(transaction=True)
def test_get_backup_of_another_workspace_is_not_found(
    api_client,
    data_fixture,
    django_capture_on_commit_callbacks,
    use_tmp_media_root,
):
    user = data_fixture.create_user()
    workspace = data_fixture.create_workspace(user=user)
    other_workspace = data_fixture.create_workspace(user=user)
    data_fixture.create_database_application(workspace=workspace)

    with django_capture_on_commit_callbacks(execute=True):
        token = data_fixture.generate_token(user)
        api_client.post(
            reverse("api:backups:start", kwargs={"workspace_id": workspace.id}),
            {},
            format="json",
            HTTP_AUTHORIZATION=f"JWT {token}",
        )

    resource_id = ImportExportResource.objects.get().id
    token = data_fixture.generate_token(user)

    response = api_client.get(
        reverse(
            "api:backups:item",
            kwargs={"workspace_id": other_workspace.id, "resource_id": resource_id},
        ),
        format="json",
        HTTP_AUTHORIZATION=f"JWT {token}",
    )

    assert response.status_code == HTTP_404_NOT_FOUND
    assert response.json()["error"] == "ERROR_RESOURCE_DOES_NOT_EXIST"


@pytest.mark.import_export_workspace
@pytest.mark.django_db(transaction=True)
def test_backup_and_restore_round_trip(
    api_client,
    data_fixture,
    django_capture_on_commit_callbacks,
    use_tmp_media_root,
):
    user = data_fixture.create_user()
    data_fixture.disable_import_signature_verification()
    workspace = data_fixture.create_workspace(user=user)
    database = data_fixture.create_database_application(
        workspace=workspace, name="Original"
    )
    table = data_fixture.create_database_table(database=database, name="People")
    field = data_fixture.create_text_field(table=table, name="Name")
    model = table.get_model()
    model.objects.create(**{f"field_{field.id}": "Ada"})

    with django_capture_on_commit_callbacks(execute=True):
        token = data_fixture.generate_token(user)
        api_client.post(
            reverse("api:backups:start", kwargs={"workspace_id": workspace.id}),
            {},
            format="json",
            HTTP_AUTHORIZATION=f"JWT {token}",
        )

    resource = ImportExportResource.objects.get()

    target = data_fixture.create_workspace(user=user)

    with django_capture_on_commit_callbacks(execute=True):
        token = data_fixture.generate_token(user)
        response = api_client.post(
            reverse("api:backups:restore", kwargs={"workspace_id": target.id}),
            {"resource_id": resource.id},
            format="json",
            HTTP_AUTHORIZATION=f"JWT {token}",
        )

    assert response.status_code == HTTP_202_ACCEPTED

    token = data_fixture.generate_token(user)
    response = api_client.get(
        reverse("api:jobs:item", kwargs={"job_id": response.json()["id"]}),
        format="json",
        HTTP_AUTHORIZATION=f"JWT {token}",
    )
    response_json = response.json()

    assert response_json["state"] == "finished"
    installed = response_json["installed_applications"]
    assert len(installed) == 1
    assert installed[0]["name"] == "Original"
    assert installed[0]["workspace"]["id"] == target.id


@pytest.mark.import_export_workspace
@pytest.mark.django_db
def test_restore_unknown_resource(api_client, data_fixture):
    user, token = data_fixture.create_user_and_token()
    workspace = data_fixture.create_workspace(user=user)

    response = api_client.post(
        reverse("api:backups:restore", kwargs={"workspace_id": workspace.id}),
        {"resource_id": 999999},
        format="json",
        HTTP_AUTHORIZATION=f"JWT {token}",
    )

    assert response.status_code == HTTP_404_NOT_FOUND
    assert response.json()["error"] == "ERROR_RESOURCE_DOES_NOT_EXIST"


@pytest.mark.import_export_workspace
@pytest.mark.django_db(transaction=True)
def test_backup_can_be_started_with_an_api_client_key(
    api_client,
    data_fixture,
    django_capture_on_commit_callbacks,
    use_tmp_media_root,
):
    user = data_fixture.create_user()
    workspace = data_fixture.create_workspace(user=user)
    data_fixture.create_database_application(workspace=workspace)
    _, raw_key = data_fixture.create_api_client_and_key(
        user=user, workspace=workspace, scopes=["backup.read", "backup.write"]
    )

    with django_capture_on_commit_callbacks(execute=True):
        response = api_client.post(
            reverse("api:backups:start", kwargs={"workspace_id": workspace.id}),
            {},
            format="json",
            HTTP_AUTHORIZATION=f"Client {raw_key}",
        )

    assert response.status_code == HTTP_202_ACCEPTED

    response = api_client.get(
        reverse("api:backups:list", kwargs={"workspace_id": workspace.id}),
        format="json",
        HTTP_AUTHORIZATION=f"Client {raw_key}",
    )

    assert response.status_code == HTTP_200_OK
    assert len(response.json()["results"]) == 1
