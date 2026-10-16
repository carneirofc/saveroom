from django.shortcuts import reverse

import pytest
from rest_framework.status import (
    HTTP_200_OK,
    HTTP_204_NO_CONTENT,
    HTTP_400_BAD_REQUEST,
    HTTP_404_NOT_FOUND,
)

from baserow.core.teams.handler import TeamHandler
from baserow.core.teams.models import Team


@pytest.fixture
def setup(data_fixture):
    admin, admin_token = data_fixture.create_user_and_token()
    member, member_token = data_fixture.create_user_and_token()
    workspace = data_fixture.create_workspace()
    data_fixture.create_user_workspace(workspace=workspace, user=admin, order=1)
    data_fixture.create_user_workspace(
        workspace=workspace, user=member, permissions="MEMBER", order=2
    )
    return workspace, admin, admin_token, member, member_token


@pytest.mark.django_db
def test_admin_can_create_and_list_teams(api_client, setup):
    workspace, admin, admin_token, member, _ = setup
    url = reverse("api:workspaces:teams:list", kwargs={"workspace_id": workspace.id})

    response = api_client.post(
        url,
        {"name": "Finance", "user_ids": [member.id]},
        format="json",
        HTTP_AUTHORIZATION=f"JWT {admin_token}",
    )
    assert response.status_code == HTTP_200_OK, response.json()
    created = response.json()
    assert created["name"] == "Finance"
    assert [m["user_id"] for m in created["members"]] == [member.id]

    response = api_client.get(url, HTTP_AUTHORIZATION=f"JWT {admin_token}")
    assert response.status_code == HTTP_200_OK
    assert [team["id"] for team in response.json()] == [created["id"]]


@pytest.mark.django_db
def test_member_cannot_manage_teams(api_client, setup):
    workspace, _, _, _, member_token = setup
    url = reverse("api:workspaces:teams:list", kwargs={"workspace_id": workspace.id})

    response = api_client.get(url, HTTP_AUTHORIZATION=f"JWT {member_token}")
    assert response.status_code == HTTP_400_BAD_REQUEST
    assert response.json()["error"] == "ERROR_USER_INVALID_GROUP_PERMISSIONS"

    response = api_client.post(
        url, {"name": "X"}, format="json", HTTP_AUTHORIZATION=f"JWT {member_token}"
    )
    assert response.status_code == HTTP_400_BAD_REQUEST
    assert not Team.objects.exists()


@pytest.mark.django_db
def test_create_team_duplicate_name_and_outsider(api_client, data_fixture, setup):
    workspace, _, admin_token, _, _ = setup
    outsider = data_fixture.create_user()
    TeamHandler().create_team(workspace, "Finance")
    url = reverse("api:workspaces:teams:list", kwargs={"workspace_id": workspace.id})

    response = api_client.post(
        url, {"name": "Finance"}, format="json", HTTP_AUTHORIZATION=f"JWT {admin_token}"
    )
    assert response.json()["error"] == "ERROR_TEAM_NAME_NOT_UNIQUE"

    response = api_client.post(
        url,
        {"name": "Sales", "user_ids": [outsider.id]},
        format="json",
        HTTP_AUTHORIZATION=f"JWT {admin_token}",
    )
    assert response.json()["error"] == "ERROR_TEAM_MEMBER_NOT_IN_WORKSPACE"


@pytest.mark.django_db
def test_rename_manage_members_and_delete_team(api_client, setup):
    workspace, admin, admin_token, member, _ = setup
    team = TeamHandler().create_team(workspace, "Finance")
    auth = {"HTTP_AUTHORIZATION": f"JWT {admin_token}"}

    item_url = reverse("api:workspaces:teams:item", kwargs={"team_id": team.id})
    members_url = reverse("api:workspaces:teams:members", kwargs={"team_id": team.id})

    response = api_client.patch(item_url, {"name": "Ops"}, format="json", **auth)
    assert response.status_code == HTTP_200_OK
    assert response.json()["name"] == "Ops"

    response = api_client.post(
        members_url, {"user_ids": [member.id, admin.id]}, format="json", **auth
    )
    assert sorted(m["user_id"] for m in response.json()["members"]) == sorted(
        [member.id, admin.id]
    )

    response = api_client.delete(
        members_url, {"user_ids": [admin.id]}, format="json", **auth
    )
    assert [m["user_id"] for m in response.json()["members"]] == [member.id]

    response = api_client.delete(item_url, **auth)
    assert response.status_code == HTTP_204_NO_CONTENT
    assert not Team.objects.exists()

    response = api_client.delete(item_url, **auth)
    assert response.status_code == HTTP_404_NOT_FOUND
    assert response.json()["error"] == "ERROR_TEAM_DOES_NOT_EXIST"


@pytest.mark.django_db
def test_admin_of_other_workspace_cannot_touch_team(api_client, data_fixture, setup):
    workspace, _, _, _, _ = setup
    other_admin, other_token = data_fixture.create_user_and_token()
    data_fixture.create_workspace(user=other_admin)
    team = TeamHandler().create_team(workspace, "Finance")

    response = api_client.patch(
        reverse("api:workspaces:teams:item", kwargs={"team_id": team.id}),
        {"name": "Hacked"},
        format="json",
        HTTP_AUTHORIZATION=f"JWT {other_token}",
    )

    assert response.status_code == HTTP_400_BAD_REQUEST
    assert response.json()["error"] == "ERROR_USER_NOT_IN_GROUP"
    team.refresh_from_db()
    assert team.name == "Finance"
