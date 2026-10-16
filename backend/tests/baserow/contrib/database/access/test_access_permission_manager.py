from django.db import connection
from django.test.utils import CaptureQueriesContext

import pytest

from baserow.contrib.database.access.exceptions import DatabaseAccessDeniedError
from baserow.contrib.database.access.permission_manager import (
    DatabaseAccessPermissionManagerType,
)
from baserow.contrib.database.table.models import Table
from baserow.core.handler import CoreHandler
from baserow.core.models import Application
from baserow.core.types import PermissionCheck

READ_TABLE = "database.table.read"
CREATE_ROW = "database.table.create_row"
CREATE_FIELD = "database.table.create_field"


def decide(user, operation, context, workspace):
    check = PermissionCheck(user, operation, context)
    result = DatabaseAccessPermissionManagerType().check_multiple_permissions(
        [check], workspace=workspace
    )
    if check not in result:
        return None
    return result[check] is True


def allowed(user, operation, context, workspace):
    return CoreHandler().check_permission_for_multiple_actors(
        [user], operation, workspace, context=context
    ) == [user]


@pytest.mark.django_db
def test_no_grants_passes_through(access_setup):
    s = access_setup

    assert decide(s.member, READ_TABLE, s.table, s.workspace) is None
    assert allowed(s.member, CREATE_FIELD, s.table, s.workspace)


@pytest.mark.django_db
def test_admins_are_never_restricted(access_setup):
    s = access_setup
    s.grant("none", user=s.admin)

    assert decide(s.admin, READ_TABLE, s.table, s.workspace) is None
    assert allowed(s.admin, CREATE_FIELD, s.table, s.workspace)


@pytest.mark.django_db
def test_non_database_operations_pass_through(access_setup):
    s = access_setup
    s.grant("none", user=s.member)

    assert decide(s.member, "workspace.read", s.workspace, s.workspace) is None


@pytest.mark.django_db
def test_most_specific_scope_wins(access_setup):
    s = access_setup
    s.grant("none", user=s.member)
    s.grant("viewer", user=s.member, database=s.database)
    s.grant("editor", user=s.member, table=s.table)

    # Table grant.
    assert decide(s.member, CREATE_ROW, s.table, s.workspace) is True
    assert decide(s.member, CREATE_FIELD, s.table, s.workspace) is False
    # Database grant.
    assert decide(s.member, READ_TABLE, s.other_table, s.workspace) is True
    assert decide(s.member, CREATE_ROW, s.other_table, s.workspace) is False
    # Workspace default.
    assert decide(s.member, READ_TABLE, s.other_database_table, s.workspace) is False


@pytest.mark.django_db
def test_user_grant_beats_team_grant_and_highest_team_wins(access_setup):
    s = access_setup
    readers = s.team("Readers", s.member)
    builders = s.team("Builders", s.member)
    s.grant("viewer", team=readers, database=s.database)
    s.grant("builder", team=builders, database=s.database)

    assert decide(s.member, CREATE_FIELD, s.table, s.workspace) is True

    s.grant("viewer", user=s.member, database=s.database)
    assert decide(s.member, CREATE_FIELD, s.table, s.workspace) is False
    assert decide(s.member, READ_TABLE, s.table, s.workspace) is True


@pytest.mark.django_db
def test_team_grants_only_apply_to_team_members(access_setup):
    s = access_setup
    outsider_member = s.add_member()
    team = s.team("Finance", s.member)
    s.grant("none", team=team)

    assert decide(s.member, READ_TABLE, s.table, s.workspace) is False
    assert decide(outsider_member, READ_TABLE, s.table, s.workspace) is None


@pytest.mark.django_db
def test_denial_is_a_permission_exception(access_setup):
    s = access_setup
    s.grant("viewer", user=s.member)
    check = PermissionCheck(s.member, CREATE_ROW, s.table)

    result = DatabaseAccessPermissionManagerType().check_multiple_permissions(
        [check], workspace=s.workspace
    )

    assert isinstance(result[check], DatabaseAccessDeniedError)
    assert not allowed(s.member, CREATE_ROW, s.table, s.workspace)


@pytest.mark.django_db
def test_contexts_below_a_table_resolve_to_their_table(access_setup, data_fixture):
    s = access_setup
    s.grant("none", user=s.member)
    s.grant("editor", user=s.member, table=s.table)
    field = data_fixture.create_text_field(table=s.table)
    view = data_fixture.create_grid_view(table=s.table)
    view_filter = data_fixture.create_view_filter(view=view, field=field)

    assert decide(s.member, "database.table.field.read", field, s.workspace) is True
    assert decide(s.member, "database.table.field.update", field, s.workspace) is False
    assert decide(s.member, "database.table.view.read", view, s.workspace) is True
    assert (
        decide(s.member, "database.table.view.filter.update", view_filter, s.workspace)
        is False
    )


@pytest.mark.django_db
def test_database_with_accessible_table_stays_reachable(access_setup):
    s = access_setup
    s.grant("none", user=s.member, database=s.database)
    s.grant("viewer", user=s.member, table=s.table)
    application = Application.objects.get(id=s.database.id)

    assert decide(s.member, "application.read", application, s.workspace) is True
    assert decide(s.member, "database.list_tables", s.database, s.workspace) is True
    assert decide(s.member, "application.update", s.database, s.workspace) is False
    assert decide(s.member, "database.create_table", s.database, s.workspace) is False
    assert decide(s.member, READ_TABLE, s.other_table, s.workspace) is False


@pytest.mark.django_db
def test_check_queries_do_not_grow_with_the_number_of_checks(
    access_setup, data_fixture
):
    s = access_setup
    s.grant("viewer", user=s.member)
    s.grant("editor", user=s.member, table=s.table)
    manager = DatabaseAccessPermissionManagerType()

    def count(tables):
        checks = [PermissionCheck(s.member, READ_TABLE, t) for t in tables]
        with CaptureQueriesContext(connection) as ctx:
            manager.check_multiple_permissions(checks, workspace=s.workspace)
        return len(ctx.captured_queries)

    # Warm the "workspace has grants" cache so both measurements hit it.
    count([s.table])
    one = count([s.table])
    many = count(
        [s.table, s.other_table]
        + [data_fixture.create_database_table(database=s.database) for _ in range(5)]
    )

    assert one == many


@pytest.mark.django_db
def test_filter_queryset_matches_individual_checks(access_setup, data_fixture):
    s = access_setup
    hidden_database = data_fixture.create_database_application(workspace=s.workspace)
    hidden_table = data_fixture.create_database_table(database=hidden_database)
    s.grant("none", user=s.member)
    s.grant("viewer", user=s.member, database=s.database)
    s.grant("none", user=s.member, table=s.other_table)
    s.grant("editor", user=s.member, table=s.other_database_table)

    tables = CoreHandler().filter_queryset(
        s.member,
        "database.list_tables",
        Table.objects.filter(database__workspace=s.workspace),
        workspace=s.workspace,
    )
    expected_tables = {
        table.id
        for table in Table.objects.filter(database__workspace=s.workspace)
        if allowed(s.member, READ_TABLE, table, s.workspace)
    }
    assert set(tables.values_list("id", flat=True)) == expected_tables
    assert expected_tables == {s.table.id, s.other_database_table.id}
    assert hidden_table.id not in expected_tables

    applications = CoreHandler().filter_queryset(
        s.member,
        "workspace.list_applications",
        Application.objects.filter(workspace=s.workspace),
        workspace=s.workspace,
    )
    expected_applications = {
        application.id
        for application in Application.objects.filter(workspace=s.workspace)
        if allowed(s.member, "application.read", application, s.workspace)
    }
    assert set(applications.values_list("id", flat=True)) == expected_applications
    assert expected_applications == {s.database.id, s.other_database.id}


@pytest.mark.django_db
def test_filter_queryset_passes_through_without_grants(access_setup):
    s = access_setup
    queryset = Table.objects.filter(database__workspace=s.workspace)

    assert (
        DatabaseAccessPermissionManagerType().filter_queryset(
            s.member, "database.list_tables", queryset, workspace=s.workspace
        )
        is None
    )


@pytest.mark.django_db
def test_permissions_object(access_setup):
    s = access_setup
    team = s.team("Finance", s.member)
    s.grant("none", team=team)
    s.grant("editor", user=s.member, table=s.table)
    manager = DatabaseAccessPermissionManagerType()

    perms = manager.get_permissions_object(s.member, workspace=s.workspace)

    assert perms["workspace"] == "none"
    assert perms["tables"] == {s.table.id: "editor"}
    assert perms["databases"] == {}
    assert perms["databases_with_accessible_tables"] == [s.database.id]
    assert CREATE_ROW in perms["level_operations"]["editor"]
    assert CREATE_ROW not in perms["level_operations"]["viewer"]
    assert manager.get_permissions_object(s.admin, workspace=s.workspace) is None


@pytest.mark.django_db
def test_grants_follow_deleted_tables_and_teams(access_setup):
    s = access_setup
    team = s.team("Finance", s.member)
    s.grant("none", team=team)
    s.grant("editor", user=s.member, table=s.table)

    s.defer_constraints()
    team.delete()
    assert decide(s.member, READ_TABLE, s.other_table, s.workspace) is None

    s.table.delete()
    assert decide(s.member, READ_TABLE, s.other_table, s.workspace) is None
