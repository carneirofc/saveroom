from unittest.mock import patch

import pytest

from baserow.contrib.database.access.handler import DatabaseAccessHandler
from baserow.core.teams.handler import TeamHandler


def _expected_payload(workspace):
    return {"type": "permissions_updated", "workspace_id": workspace.id}


@pytest.fixture
def members(data_fixture):
    workspace = data_fixture.create_workspace()
    admin = data_fixture.create_user()
    member = data_fixture.create_user()
    teammate = data_fixture.create_user()
    data_fixture.create_user_workspace(workspace=workspace, user=admin, order=1)
    for order, user in enumerate([member, teammate], start=2):
        data_fixture.create_user_workspace(
            workspace=workspace, user=user, permissions="MEMBER", order=order
        )
    return workspace, member, teammate


@pytest.mark.django_db(transaction=True)
@pytest.mark.websockets
@patch("baserow.ws.signals.broadcast_to_users")
def test_team_membership_changes_broadcast_permissions_updated(
    mock_broadcast_to_users, members
):
    workspace, member, _ = members
    team = TeamHandler().create_team(workspace, "Finance")
    mock_broadcast_to_users.delay.assert_not_called()

    TeamHandler().add_members(team, [member.id])
    mock_broadcast_to_users.delay.assert_called_once_with(
        [member.id], _expected_payload(workspace)
    )

    mock_broadcast_to_users.reset_mock()
    TeamHandler().remove_members(team, [member.id])
    mock_broadcast_to_users.delay.assert_called_once_with(
        [member.id], _expected_payload(workspace)
    )


@pytest.mark.django_db(transaction=True)
@pytest.mark.websockets
@patch("baserow.ws.signals.broadcast_to_users")
def test_noop_team_changes_do_not_broadcast(mock_broadcast_to_users, members):
    workspace, member, _ = members
    team = TeamHandler().create_team(workspace, "Finance", [member.id])
    mock_broadcast_to_users.reset_mock()

    # Already a member, and removing someone who isn't in the team.
    TeamHandler().add_members(team, [member.id])
    TeamHandler().remove_members(team, [0])

    mock_broadcast_to_users.delay.assert_not_called()


@pytest.mark.django_db(transaction=True)
@pytest.mark.websockets
@patch("baserow.ws.signals.broadcast_to_users")
def test_setting_grants_broadcasts_to_members_and_team_members(
    mock_broadcast_to_users, data_fixture, members
):
    workspace, member, teammate = members
    team = TeamHandler().create_team(workspace, "Finance", [teammate.id])
    database = data_fixture.create_database_application(workspace=workspace)
    mock_broadcast_to_users.reset_mock()

    handler = DatabaseAccessHandler()
    handler.set_grants(
        handler.get_scope("database", database.id),
        [
            {"subject_type": "user", "subject_id": member.id, "level": "viewer"},
            {"subject_type": "team", "subject_id": team.id, "level": "none"},
        ],
    )

    mock_broadcast_to_users.delay.assert_called_once()
    user_ids, payload = mock_broadcast_to_users.delay.call_args.args
    assert sorted(user_ids) == sorted([member.id, teammate.id])
    assert payload == _expected_payload(workspace)
