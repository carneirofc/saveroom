import pytest

from baserow.contrib.database.access.resolver import (
    invalidate_workspace_grants_cache,
    load_effective_access,
    workspace_has_grants,
)


@pytest.mark.django_db
def test_grants_exist_cache_follows_creates_and_deletes(access_setup):
    s = access_setup
    invalidate_workspace_grants_cache(s.workspace.id)
    assert workspace_has_grants(s.workspace.id) is False

    grant = s.grant("viewer", user=s.member)
    assert workspace_has_grants(s.workspace.id) is True

    grant.delete()
    assert workspace_has_grants(s.workspace.id) is False


@pytest.mark.django_db
@pytest.mark.parametrize("deleted", ["table", "database", "team", "user"])
def test_grants_exist_cache_follows_cascading_deletes(access_setup, deleted):
    s = access_setup
    team = s.team("Finance", s.member)
    subject = {"team": team} if deleted == "team" else {"user": s.member}
    scope = {"database": s.database} if deleted == "database" else {"table": s.table}
    s.grant("none", **subject, **scope)
    assert workspace_has_grants(s.workspace.id) is True

    s.defer_constraints()
    {
        "table": s.table,
        "database": s.database,
        "team": team,
        "user": s.member,
    }[deleted].delete()

    assert workspace_has_grants(s.workspace.id) is False


@pytest.mark.django_db
def test_workspace_without_grants_costs_no_queries(
    access_setup, django_assert_num_queries
):
    s = access_setup
    invalidate_workspace_grants_cache(s.workspace.id)
    workspace_has_grants(s.workspace.id)

    with django_assert_num_queries(0):
        assert load_effective_access(s.workspace, [s.member.id]) == {}


@pytest.mark.django_db
def test_grants_of_other_workspaces_do_not_leak(access_setup, data_fixture):
    s = access_setup
    other_workspace = data_fixture.create_workspace()
    data_fixture.create_user_workspace(
        workspace=other_workspace, user=s.member, permissions="MEMBER"
    )
    s.grant("none", user=s.member)

    assert load_effective_access(other_workspace, [s.member.id]) == {}
    assert s.member.id in load_effective_access(s.workspace, [s.member.id])
