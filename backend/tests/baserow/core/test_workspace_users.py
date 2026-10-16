from unittest.mock import patch

import pytest

from baserow.core.exceptions import (
    UserInvalidWorkspacePermissionsError,
    UserNotInWorkspace,
)
from baserow.core.models import WorkspaceUser
from baserow.core.teams.exceptions import TeamDoesNotExist
from baserow.core.teams.handler import TeamHandler
from baserow.core.workspace_users import (
    CANDIDATE_SEARCH_LIMIT,
    UsersNotFound,
    WorkspaceUsersService,
)


@pytest.fixture
def workspace_setup(data_fixture):
    admin = data_fixture.create_user(first_name="Admin")
    member = data_fixture.create_user(first_name="Member")
    workspace = data_fixture.create_workspace()
    data_fixture.create_user_workspace(workspace=workspace, user=admin, order=1)
    data_fixture.create_user_workspace(
        workspace=workspace, user=member, permissions="MEMBER", order=2
    )
    return workspace, admin, member


@pytest.mark.django_db
def test_search_candidates_matches_name_or_email_case_insensitively(
    data_fixture, workspace_setup
):
    workspace, admin, _ = workspace_setup
    by_name = data_fixture.create_user(first_name="Johanna", email="j@example.com")
    by_email = data_fixture.create_user(first_name="X", email="johan@example.com")
    data_fixture.create_user(first_name="Other", email="other@example.com")

    result = WorkspaceUsersService().search_candidates(admin, workspace, "  JOHAN ")

    assert {user.id for user in result} == {by_name.id, by_email.id}


@pytest.mark.django_db
def test_search_candidates_excludes_members_inactive_and_deleted_accounts(
    data_fixture, workspace_setup
):
    workspace, admin, member = workspace_setup
    data_fixture.create_user(first_name="Sam Inactive", is_active=False)
    to_be_deleted = data_fixture.create_user(first_name="Sam Leaving")
    to_be_deleted.profile.to_be_deleted = True
    to_be_deleted.profile.save()
    member.first_name = "Sam Member"
    member.save()
    candidate = data_fixture.create_user(first_name="Sam Candidate")

    result = WorkspaceUsersService().search_candidates(admin, workspace, "Sam")

    assert [user.id for user in result] == [candidate.id]


@pytest.mark.django_db
def test_search_candidates_requires_a_minimum_length_and_is_limited(
    data_fixture, workspace_setup
):
    workspace, admin, _ = workspace_setup
    for index in range(CANDIDATE_SEARCH_LIMIT + 5):
        data_fixture.create_user(first_name=f"Bulk {index}")

    service = WorkspaceUsersService()

    assert list(service.search_candidates(admin, workspace, "Bu")) == []
    assert len(service.search_candidates(admin, workspace, "Bulk")) == (
        CANDIDATE_SEARCH_LIMIT
    )


@pytest.mark.django_db
def test_only_workspace_admins_can_search_or_add(data_fixture, workspace_setup):
    workspace, _, member = workspace_setup
    outsider = data_fixture.create_user()
    candidate = data_fixture.create_user(first_name="Candidate")
    service = WorkspaceUsersService()

    with pytest.raises(UserInvalidWorkspacePermissionsError):
        service.search_candidates(member, workspace, "Candidate")
    with pytest.raises(UserInvalidWorkspacePermissionsError):
        service.add_users(member, workspace, [candidate.id])
    with pytest.raises(UserNotInWorkspace):
        service.add_users(outsider, workspace, [candidate.id])

    assert not WorkspaceUser.objects.filter(user=candidate).exists()


@pytest.mark.django_db
def test_add_users_creates_memberships_with_permissions(data_fixture, workspace_setup):
    workspace, admin, _ = workspace_setup
    alice = data_fixture.create_user()
    bob = data_fixture.create_user()

    with patch("baserow.core.handler.workspace_user_added.send") as added:
        workspace_users = WorkspaceUsersService().add_users(
            admin, workspace, [alice.id, bob.id], "ADMIN"
        )

    assert {wu.user_id for wu in workspace_users} == {alice.id, bob.id}
    assert {wu.permissions for wu in workspace_users} == {"ADMIN"}
    # Each new membership notifies the workspace in real time.
    assert added.call_count == 2


@pytest.mark.django_db
def test_add_users_keeps_existing_memberships_untouched(data_fixture, workspace_setup):
    workspace, admin, member = workspace_setup

    with patch("baserow.core.handler.workspace_user_added.send") as added:
        (workspace_user,) = WorkspaceUsersService().add_users(
            admin, workspace, [member.id], "ADMIN"
        )

    assert workspace_user.permissions == "MEMBER"
    added.assert_not_called()


@pytest.mark.django_db
def test_add_users_is_all_or_nothing(data_fixture, workspace_setup):
    workspace, admin, _ = workspace_setup
    alice = data_fixture.create_user()
    inactive = data_fixture.create_user(is_active=False)

    with pytest.raises(UsersNotFound) as exc:
        WorkspaceUsersService().add_users(admin, workspace, [alice.id, inactive.id, 0])

    assert exc.value.user_ids == [0, inactive.id]
    assert not WorkspaceUser.objects.filter(user=alice).exists()


@pytest.mark.django_db
def test_add_users_joins_teams_and_skips_null_options(data_fixture, workspace_setup):
    workspace, admin, _ = workspace_setup
    alice = data_fixture.create_user()
    team = TeamHandler().create_team(workspace, "Ops")

    WorkspaceUsersService().add_users(
        admin, workspace, [alice.id], team_ids=[team.id], options={"access_level": None}
    )

    assert list(team.members.values_list("user_id", flat=True)) == [alice.id]


@pytest.mark.django_db
def test_add_users_with_unknown_team_raises(data_fixture, workspace_setup):
    workspace, admin, _ = workspace_setup
    alice = data_fixture.create_user()

    with pytest.raises(TeamDoesNotExist):
        WorkspaceUsersService().add_users(admin, workspace, [alice.id], team_ids=[0])
