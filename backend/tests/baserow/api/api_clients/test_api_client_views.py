from datetime import timedelta

from django.urls import reverse
from django.utils import timezone

import pytest
from rest_framework.status import (
    HTTP_200_OK,
    HTTP_204_NO_CONTENT,
    HTTP_400_BAD_REQUEST,
    HTTP_401_UNAUTHORIZED,
    HTTP_403_FORBIDDEN,
    HTTP_404_NOT_FOUND,
)

from baserow.core.api_clients.handler import ApiClientHandler
from baserow.core.api_clients.models import ApiClientKey


@pytest.mark.django_db
def test_create_api_client(api_client, data_fixture):
    user, token = data_fixture.create_user_and_token()
    workspace = data_fixture.create_workspace(user=user)

    response = api_client.post(
        reverse("api:api_clients:list", kwargs={"workspace_id": workspace.id}),
        {"name": "Nightly backups", "scopes": ["backup.write", "backup.read"]},
        format="json",
        HTTP_AUTHORIZATION=f"JWT {token}",
    )

    assert response.status_code == HTTP_200_OK
    response_json = response.json()
    assert response_json["name"] == "Nightly backups"
    # The scopes come back in the canonical order, not the order they were sent in.
    assert response_json["scopes"] == ["backup.read", "backup.write"]
    assert response_json["is_active"] is True
    assert response_json["keys"] == []


@pytest.mark.django_db
def test_create_api_client_with_unknown_scope(api_client, data_fixture):
    user, token = data_fixture.create_user_and_token()
    workspace = data_fixture.create_workspace(user=user)

    response = api_client.post(
        reverse("api:api_clients:list", kwargs={"workspace_id": workspace.id}),
        {"name": "Bad", "scopes": ["backup.everything"]},
        format="json",
        HTTP_AUTHORIZATION=f"JWT {token}",
    )

    assert response.status_code == HTTP_400_BAD_REQUEST
    assert response.json()["error"] == "ERROR_REQUEST_BODY_VALIDATION"


@pytest.mark.django_db
def test_create_api_client_in_other_users_workspace(api_client, data_fixture):
    data_fixture.create_user()
    _, token = data_fixture.create_user_and_token()
    workspace = data_fixture.create_workspace()

    response = api_client.post(
        reverse("api:api_clients:list", kwargs={"workspace_id": workspace.id}),
        {"name": "Sneaky", "scopes": []},
        format="json",
        HTTP_AUTHORIZATION=f"JWT {token}",
    )

    assert response.status_code == HTTP_400_BAD_REQUEST
    assert response.json()["error"] == "ERROR_USER_NOT_IN_GROUP"


@pytest.mark.django_db
def test_list_api_clients_only_returns_own_clients(api_client, data_fixture):
    user, token = data_fixture.create_user_and_token()
    other_user = data_fixture.create_user()
    workspace = data_fixture.create_workspace(users=[user, other_user])

    mine = data_fixture.create_api_client(user=user, workspace=workspace)
    data_fixture.create_api_client(user=other_user, workspace=workspace)

    response = api_client.get(
        reverse("api:api_clients:list", kwargs={"workspace_id": workspace.id}),
        format="json",
        HTTP_AUTHORIZATION=f"JWT {token}",
    )

    assert response.status_code == HTTP_200_OK
    response_json = response.json()
    assert [entry["id"] for entry in response_json] == [mine.id]


@pytest.mark.django_db
def test_create_key_returns_the_secret_exactly_once(api_client, data_fixture):
    user, token = data_fixture.create_user_and_token()
    workspace = data_fixture.create_workspace(user=user)
    client = data_fixture.create_api_client(user=user, workspace=workspace)

    response = api_client.post(
        reverse("api:api_clients:keys", kwargs={"client_id": client.id}),
        {"name": "ci"},
        format="json",
        HTTP_AUTHORIZATION=f"JWT {token}",
    )

    assert response.status_code == HTTP_200_OK
    response_json = response.json()
    raw_key = response_json["key"]
    assert raw_key.startswith(response_json["prefix"] + ".")

    # The secret itself is never stored, only its hash.
    stored = ApiClientKey.objects.get(id=response_json["id"])
    assert stored.hashed_secret != raw_key
    assert stored.hashed_secret == ApiClientHandler().hash_secret(
        raw_key.split(".", 1)[1]
    )

    # Reading the client back never exposes the secret again.
    response = api_client.get(
        reverse("api:api_clients:item", kwargs={"client_id": client.id}),
        format="json",
        HTTP_AUTHORIZATION=f"JWT {token}",
    )
    assert "key" not in response.json()["keys"][0]


@pytest.mark.django_db
def test_cannot_manage_another_users_client(api_client, data_fixture):
    owner = data_fixture.create_user()
    other_user, other_token = data_fixture.create_user_and_token()
    workspace = data_fixture.create_workspace(users=[owner, other_user])
    client = data_fixture.create_api_client(user=owner, workspace=workspace)

    response = api_client.patch(
        reverse("api:api_clients:item", kwargs={"client_id": client.id}),
        {"name": "Hijacked"},
        format="json",
        HTTP_AUTHORIZATION=f"JWT {other_token}",
    )

    assert response.status_code == HTTP_404_NOT_FOUND
    assert response.json()["error"] == "ERROR_API_CLIENT_DOES_NOT_EXIST"


@pytest.mark.django_db
def test_revoke_key_stops_it_from_working(api_client, data_fixture):
    user, token = data_fixture.create_user_and_token()
    workspace = data_fixture.create_workspace(user=user)
    client = data_fixture.create_api_client(user=user, workspace=workspace)
    key, raw_key = ApiClientHandler().create_key(user, client)

    response = api_client.get(
        reverse("api:backups:list", kwargs={"workspace_id": workspace.id}),
        format="json",
        HTTP_AUTHORIZATION=f"Client {raw_key}",
    )
    assert response.status_code == HTTP_200_OK

    response = api_client.delete(
        reverse("api:api_clients:key_item", kwargs={"key_id": key.id}),
        format="json",
        HTTP_AUTHORIZATION=f"JWT {token}",
    )
    assert response.status_code == HTTP_200_OK
    assert response.json()["revoked_on"] is not None

    response = api_client.get(
        reverse("api:backups:list", kwargs={"workspace_id": workspace.id}),
        format="json",
        HTTP_AUTHORIZATION=f"Client {raw_key}",
    )
    assert response.status_code == HTTP_401_UNAUTHORIZED
    assert response.json()["error"] == "ERROR_INVALID_API_CLIENT_KEY"


@pytest.mark.django_db
def test_delete_api_client_removes_its_keys(api_client, data_fixture):
    user, token = data_fixture.create_user_and_token()
    workspace = data_fixture.create_workspace(user=user)
    client = data_fixture.create_api_client(user=user, workspace=workspace)
    key, _ = ApiClientHandler().create_key(user, client)

    response = api_client.delete(
        reverse("api:api_clients:item", kwargs={"client_id": client.id}),
        format="json",
        HTTP_AUTHORIZATION=f"JWT {token}",
    )

    assert response.status_code == HTTP_204_NO_CONTENT
    assert not ApiClientKey.objects.filter(id=key.id).exists()


@pytest.mark.django_db
def test_key_authenticates_as_the_owning_user(api_client, data_fixture):
    user = data_fixture.create_user()
    workspace = data_fixture.create_workspace(user=user)
    client, raw_key = data_fixture.create_api_client_and_key(
        user=user, workspace=workspace
    )

    response = api_client.get(
        reverse("api:backups:list", kwargs={"workspace_id": workspace.id}),
        format="json",
        HTTP_AUTHORIZATION=f"Client {raw_key}",
    )

    assert response.status_code == HTTP_200_OK
    assert response.json() == {"results": []}


@pytest.mark.django_db
def test_key_without_the_required_scope_is_refused(api_client, data_fixture):
    user = data_fixture.create_user()
    workspace = data_fixture.create_workspace(user=user)
    client, raw_key = data_fixture.create_api_client_and_key(
        user=user, workspace=workspace, scopes=["contents.read"]
    )

    response = api_client.get(
        reverse("api:backups:list", kwargs={"workspace_id": workspace.id}),
        format="json",
        HTTP_AUTHORIZATION=f"Client {raw_key}",
    )

    assert response.status_code == HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_inactive_client_is_refused(api_client, data_fixture):
    user = data_fixture.create_user()
    workspace = data_fixture.create_workspace(user=user)
    client, raw_key = data_fixture.create_api_client_and_key(
        user=user, workspace=workspace
    )

    client.is_active = False
    client.save()

    response = api_client.get(
        reverse("api:backups:list", kwargs={"workspace_id": workspace.id}),
        format="json",
        HTTP_AUTHORIZATION=f"Client {raw_key}",
    )

    assert response.status_code == HTTP_401_UNAUTHORIZED
    assert response.json()["error"] == "ERROR_INVALID_API_CLIENT_KEY"


@pytest.mark.django_db
def test_expired_key_is_refused(api_client, data_fixture):
    user = data_fixture.create_user()
    workspace = data_fixture.create_workspace(user=user)
    client = data_fixture.create_api_client(user=user, workspace=workspace)
    key, raw_key = ApiClientHandler().create_key(
        user, client, expires_on=timezone.now() + timedelta(hours=1)
    )

    key.expires_on = timezone.now() - timedelta(seconds=1)
    key.save()

    response = api_client.get(
        reverse("api:backups:list", kwargs={"workspace_id": workspace.id}),
        format="json",
        HTTP_AUTHORIZATION=f"Client {raw_key}",
    )

    assert response.status_code == HTTP_401_UNAUTHORIZED
    assert response.json()["error"] == "ERROR_INVALID_API_CLIENT_KEY"


@pytest.mark.django_db
@pytest.mark.parametrize(
    "raw_key",
    ["nonsense", "noseparator", "unknownp.somesecretthatdoesnotexist"],
)
def test_malformed_or_unknown_key_is_refused(api_client, data_fixture, raw_key):
    user = data_fixture.create_user()
    workspace = data_fixture.create_workspace(user=user)

    response = api_client.get(
        reverse("api:backups:list", kwargs={"workspace_id": workspace.id}),
        format="json",
        HTTP_AUTHORIZATION=f"Client {raw_key}",
    )

    assert response.status_code == HTTP_401_UNAUTHORIZED
    assert response.json()["error"] == "ERROR_INVALID_API_CLIENT_KEY"


@pytest.mark.django_db
def test_key_with_the_wrong_secret_is_refused(api_client, data_fixture):
    user = data_fixture.create_user()
    workspace = data_fixture.create_workspace(user=user)
    client, raw_key = data_fixture.create_api_client_and_key(
        user=user, workspace=workspace
    )
    prefix = raw_key.split(".", 1)[0]

    response = api_client.get(
        reverse("api:backups:list", kwargs={"workspace_id": workspace.id}),
        format="json",
        HTTP_AUTHORIZATION=f"Client {prefix}.thisisnottherightsecretatall",
    )

    assert response.status_code == HTTP_401_UNAUTHORIZED
    assert response.json()["error"] == "ERROR_INVALID_API_CLIENT_KEY"
