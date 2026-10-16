from django.shortcuts import reverse

import pytest
from rest_framework.status import (
    HTTP_200_OK,
    HTTP_400_BAD_REQUEST,
    HTTP_404_NOT_FOUND,
)

from baserow.contrib.database.access.models import DatabaseAccessGrant
from baserow.core.models import WorkspaceUser
from baserow.core.teams.handler import TeamHandler
from baserow.core.teams.models import TeamMember


@pytest.fixture
def setup(data_fixture):
    admin, admin_token = data_fixture.create_user_and_token(first_name="Admin")
    member, member_token = data_fixture.create_user_and_token(first_name="Member")
    workspace = data_fixture.create_workspace()
    data_fixture.create_user_workspace(workspace=workspace, user=admin, order=1)
    data_fixture.create_user_workspace(
        workspace=workspace, user=member, permissions="MEMBER", order=2
    )
    return workspace, admin_token, member, member_token


def add_url(workspace):
    return reverse("api:workspaces:users:list", kwargs={"workspace_id": workspace.id})


def candidates_url(workspace, search):
    return (
        reverse(
            "api:workspaces:users:candidates", kwargs={"workspace_id": workspace.id}
        )
        + f"?search={search}"
    )


@pytest.mark.django_db
def test_admin_adds_existing_users_directly(api_client, data_fixture, setup):
    workspace, admin_token, member, _ = setup
    alice = data_fixture.create_user(email="alice@example.com")
    bob = data_fixture.create_user(email="bob@example.com")

    response = api_client.post(
        add_url(workspace),
        {"user_ids": [alice.id, bob.id], "permissions": "ADMIN"},
        format="json",
        HTTP_AUTHORIZATION=f"JWT {admin_token}",
    )

    assert response.status_code == HTTP_200_OK, response.json()
    assert sorted(item["user_id"] for item in response.json()) == sorted(
        [alice.id, bob.id]
    )
    assert set(
        WorkspaceUser.objects.filter(
            workspace=workspace, user__in=[alice, bob]
        ).values_list("permissions", flat=True)
    ) == {"ADMIN"}


@pytest.mark.django_db
def test_adding_an_existing_member_keeps_their_permissions(
    api_client, data_fixture, setup
):
    workspace, admin_token, member, _ = setup

    response = api_client.post(
        add_url(workspace),
        {"user_ids": [member.id], "permissions": "ADMIN"},
        format="json",
        HTTP_AUTHORIZATION=f"JWT {admin_token}",
    )

    assert response.status_code == HTTP_200_OK
    assert WorkspaceUser.objects.get(workspace=workspace, user=member).permissions == (
        "MEMBER"
    )


@pytest.mark.django_db
def test_add_users_defaults_to_member_and_refuses_unaddable_accounts(
    api_client, data_fixture, setup
):
    workspace, admin_token, _, _ = setup
    alice = data_fixture.create_user()
    inactive = data_fixture.create_user(is_active=False)

    response = api_client.post(
        add_url(workspace),
        {"user_ids": [alice.id, inactive.id, 0]},
        format="json",
        HTTP_AUTHORIZATION=f"JWT {admin_token}",
    )

    assert response.status_code == HTTP_400_BAD_REQUEST
    assert response.json()["error"] == "ERROR_USERS_CANNOT_BE_ADDED"
    # All or nothing.
    assert not WorkspaceUser.objects.filter(workspace=workspace, user=alice).exists()

    response = api_client.post(
        add_url(workspace),
        {"user_ids": [alice.id]},
        format="json",
        HTTP_AUTHORIZATION=f"JWT {admin_token}",
    )
    assert response.json()[0]["permissions"] == "MEMBER"


@pytest.mark.django_db
def test_member_cannot_add_users_or_search(api_client, data_fixture, setup):
    workspace, _, _, member_token = setup
    alice = data_fixture.create_user(email="alice@example.com")

    response = api_client.post(
        add_url(workspace),
        {"user_ids": [alice.id]},
        format="json",
        HTTP_AUTHORIZATION=f"JWT {member_token}",
    )
    assert response.status_code == HTTP_400_BAD_REQUEST
    assert response.json()["error"] == "ERROR_USER_INVALID_GROUP_PERMISSIONS"

    response = api_client.get(
        candidates_url(workspace, "alice"), HTTP_AUTHORIZATION=f"JWT {member_token}"
    )
    assert response.status_code == HTTP_400_BAD_REQUEST
    assert response.json()["error"] == "ERROR_USER_INVALID_GROUP_PERMISSIONS"


@pytest.mark.django_db
def test_candidates_search(api_client, data_fixture, setup):
    workspace, admin_token, member, _ = setup
    alice = data_fixture.create_user(email="alice@example.com", first_name="Alice")
    data_fixture.create_user(email="alice.gone@example.com", is_active=False)
    auth = {"HTTP_AUTHORIZATION": f"JWT {admin_token}"}

    response = api_client.get(candidates_url(workspace, "ALICE"), **auth)
    assert response.status_code == HTTP_200_OK, response.json()
    assert response.json() == [
        {"user_id": alice.id, "name": "Alice", "email": "alice@example.com"}
    ]

    # Existing members are not candidates.
    response = api_client.get(candidates_url(workspace, member.email[:5]), **auth)
    assert member.id not in [item["user_id"] for item in response.json()]

    # A minimum length keeps admins from listing every account.
    response = api_client.get(candidates_url(workspace, "al"), **auth)
    assert response.status_code == HTTP_400_BAD_REQUEST
    assert response.json()["error"] == "ERROR_QUERY_PARAMETER_VALIDATION"


@pytest.mark.django_db
def test_admin_adds_users_into_teams_with_a_default_access_level(
    api_client, data_fixture, setup
):
    workspace, admin_token, member, _ = setup
    alice = data_fixture.create_user(email="alice@example.com")
    team = TeamHandler().create_team(workspace, "Finance")

    response = api_client.post(
        add_url(workspace),
        {
            "user_ids": [alice.id, member.id],
            "team_ids": [team.id],
            "access_level": "viewer",
        },
        format="json",
        HTTP_AUTHORIZATION=f"JWT {admin_token}",
    )

    assert response.status_code == HTTP_200_OK, response.json()
    assert set(
        TeamMember.objects.filter(team=team).values_list("user_id", flat=True)
    ) == {alice.id, member.id}
    assert set(
        DatabaseAccessGrant.objects.filter(
            workspace=workspace, database=None, table=None, team=None
        ).values_list("user_id", "level")
    ) == {(alice.id, "viewer"), (member.id, "viewer")}


@pytest.mark.django_db
def test_add_users_with_a_team_of_another_workspace_adds_nothing(
    api_client, data_fixture, setup
):
    workspace, admin_token, _, _ = setup
    alice = data_fixture.create_user()
    other_team = TeamHandler().create_team(data_fixture.create_workspace(), "Other")

    response = api_client.post(
        add_url(workspace),
        {"user_ids": [alice.id], "team_ids": [other_team.id]},
        format="json",
        HTTP_AUTHORIZATION=f"JWT {admin_token}",
    )

    assert response.status_code == HTTP_404_NOT_FOUND
    assert response.json()["error"] == "ERROR_TEAM_DOES_NOT_EXIST"
    assert not WorkspaceUser.objects.filter(workspace=workspace, user=alice).exists()


@pytest.mark.django_db
def test_add_users_refuses_an_unknown_access_level(api_client, data_fixture, setup):
    workspace, admin_token, _, _ = setup
    alice = data_fixture.create_user()

    response = api_client.post(
        add_url(workspace),
        {"user_ids": [alice.id], "access_level": "owner"},
        format="json",
        HTTP_AUTHORIZATION=f"JWT {admin_token}",
    )

    assert response.status_code == HTTP_400_BAD_REQUEST
    assert response.json()["error"] == "ERROR_REQUEST_BODY_VALIDATION"
    assert not WorkspaceUser.objects.filter(workspace=workspace, user=alice).exists()


@pytest.mark.django_db
def test_members_listing_includes_teams_and_default_access(
    api_client, data_fixture, setup
):
    workspace, admin_token, member, _ = setup
    team = TeamHandler().create_team(workspace, "Finance", [member.id])
    DatabaseAccessGrant.objects.create(workspace=workspace, user=member, level="editor")

    response = api_client.get(
        add_url(workspace), HTTP_AUTHORIZATION=f"JWT {admin_token}"
    )

    assert response.status_code == HTTP_200_OK, response.json()
    by_user = {item["user_id"]: item for item in response.json()}
    assert by_user[member.id]["teams"] == [{"id": team.id, "name": "Finance"}]
    assert by_user[member.id]["access_level"] == "editor"
    admin_entry = next(item for uid, item in by_user.items() if uid != member.id)
    assert admin_entry["teams"] == []
    assert admin_entry["access_level"] is None
