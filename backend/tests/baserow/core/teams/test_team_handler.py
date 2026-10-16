from unittest.mock import patch

import pytest

from baserow.core.handler import CoreHandler
from baserow.core.teams.exceptions import (
    TeamMemberNotInWorkspace,
    TeamNameNotUnique,
)
from baserow.core.teams.handler import TeamHandler
from baserow.core.teams.models import Team, TeamMember, sso_team_member_source


@pytest.fixture
def workspace_with_members(data_fixture):
    workspace = data_fixture.create_workspace()
    admin = data_fixture.create_user()
    member = data_fixture.create_user()
    data_fixture.create_user_workspace(workspace=workspace, user=admin, order=1)
    data_fixture.create_user_workspace(
        workspace=workspace, user=member, permissions="MEMBER", order=2
    )
    return workspace, admin, member


@pytest.mark.django_db
def test_create_team_with_members(workspace_with_members):
    workspace, admin, member = workspace_with_members

    team = TeamHandler().create_team(workspace, "  Finance ", [member.id])

    assert team.name == "Finance"
    assert list(team.members.values_list("user_id", "source")) == [
        (member.id, "manual")
    ]


@pytest.mark.django_db
def test_create_team_name_must_be_unique_per_workspace(
    data_fixture, workspace_with_members
):
    workspace, _, _ = workspace_with_members
    TeamHandler().create_team(workspace, "Finance")

    with pytest.raises(TeamNameNotUnique):
        TeamHandler().create_team(workspace, "Finance")

    other_workspace = data_fixture.create_workspace()
    assert TeamHandler().create_team(other_workspace, "Finance").id


@pytest.mark.django_db
def test_update_team_rejects_duplicate_name(workspace_with_members):
    workspace, _, _ = workspace_with_members
    TeamHandler().create_team(workspace, "Finance")
    team = TeamHandler().create_team(workspace, "Sales")

    with pytest.raises(TeamNameNotUnique):
        TeamHandler().update_team(team, "Finance")

    assert TeamHandler().update_team(team, "Ops").name == "Ops"


@pytest.mark.django_db
def test_add_members_refuses_users_outside_the_workspace(
    data_fixture, workspace_with_members
):
    workspace, _, member = workspace_with_members
    outsider = data_fixture.create_user()
    team = TeamHandler().create_team(workspace, "Finance")

    with pytest.raises(TeamMemberNotInWorkspace):
        TeamHandler().add_members(team, [member.id, outsider.id])

    assert not team.members.exists()


@pytest.mark.django_db
def test_add_members_keeps_existing_membership_source(workspace_with_members):
    workspace, _, member = workspace_with_members
    team = TeamHandler().create_team(workspace, "Finance", [member.id])

    new_members = TeamHandler().add_members(
        team, [member.id], source=sso_team_member_source(1)
    )

    assert new_members == []
    assert team.members.get().source == "manual"


@pytest.mark.django_db
def test_remove_members_by_source_only_removes_that_source(
    data_fixture, workspace_with_members
):
    workspace, admin, member = workspace_with_members
    team = TeamHandler().create_team(workspace, "Finance", [admin.id])
    TeamHandler().add_members(team, [member.id], source=sso_team_member_source(1))

    removed = TeamHandler().remove_members(
        team, [admin.id, member.id], source=sso_team_member_source(1)
    )

    assert removed == 1
    assert list(team.members.values_list("user_id", flat=True)) == [admin.id]


@pytest.mark.django_db
def test_member_changes_notify_affected_users(workspace_with_members):
    workspace, admin, member = workspace_with_members
    team = TeamHandler().create_team(workspace, "Finance")

    with patch("baserow.core.teams.handler.permissions_updated.send") as send:
        TeamHandler().add_members(team, [member.id])
    send.assert_called_once()
    assert send.call_args.kwargs["user_ids"] == [member.id]

    with patch("baserow.core.teams.handler.permissions_updated.send") as send:
        TeamHandler().delete_team(team)
    assert send.call_args.kwargs["user_ids"] == [member.id]


@pytest.mark.django_db
def test_removing_workspace_user_removes_its_team_memberships(
    data_fixture, workspace_with_members
):
    workspace, admin, member = workspace_with_members
    team = TeamHandler().create_team(workspace, "Finance", [member.id])
    other_workspace = data_fixture.create_workspace()
    data_fixture.create_user_workspace(
        workspace=other_workspace, user=member, permissions="MEMBER"
    )
    other_team = TeamHandler().create_team(other_workspace, "Finance", [member.id])

    workspace_user = CoreHandler().get_workspace_user(
        workspace.workspaceuser_set.get(user=member).id
    )
    CoreHandler().delete_workspace_user(admin, workspace_user)

    assert not TeamMember.objects.filter(team=team).exists()
    assert TeamMember.objects.filter(team=other_team, user=member).exists()


@pytest.mark.django_db
def test_deleting_workspace_deletes_teams(workspace_with_members):
    workspace, _, member = workspace_with_members
    TeamHandler().create_team(workspace, "Finance", [member.id])

    workspace.delete()

    assert not Team.objects.exists()
    assert not TeamMember.objects.exists()
