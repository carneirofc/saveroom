from unittest.mock import patch

import pytest

from baserow.contrib.database.access.exceptions import (
    InvalidAccessScope,
    InvalidAccessSubject,
)
from baserow.contrib.database.access.handler import DatabaseAccessHandler
from baserow.contrib.database.access.models import DatabaseAccessGrant


@pytest.mark.django_db
def test_get_scope(access_setup, data_fixture):
    s = access_setup
    handler = DatabaseAccessHandler()

    assert handler.get_scope("workspace", s.workspace.id).workspace == s.workspace
    assert handler.get_scope("database", s.database.id).database == s.database
    scope = handler.get_scope("table", s.table.id)
    assert scope.table == s.table and scope.workspace == s.workspace

    with pytest.raises(InvalidAccessScope):
        handler.get_scope("table", 0)

    template_database = data_fixture.create_database_application(workspace=None)
    with pytest.raises(InvalidAccessScope):
        handler.get_scope("database", template_database.id)


@pytest.mark.django_db
def test_set_grants_creates_updates_and_removes(access_setup):
    s = access_setup
    team = s.team("Finance", s.member)
    handler = DatabaseAccessHandler()
    scope = handler.get_scope("table", s.table.id)

    handler.set_grants(
        scope,
        [
            {"subject_type": "user", "subject_id": s.member.id, "level": "viewer"},
            {"subject_type": "team", "subject_id": team.id, "level": "editor"},
        ],
    )
    assert handler.get_scope_grants(scope) == {
        ("user", s.member.id): "viewer",
        ("team", team.id): "editor",
    }

    handler.set_grants(
        scope,
        [
            {"subject_type": "user", "subject_id": s.member.id, "level": "builder"},
            {"subject_type": "team", "subject_id": team.id, "level": None},
        ],
    )
    assert handler.get_scope_grants(scope) == {("user", s.member.id): "builder"}
    assert DatabaseAccessGrant.objects.count() == 1


@pytest.mark.django_db
def test_set_grants_refuses_foreign_subjects(access_setup, data_fixture):
    s = access_setup
    outsider = data_fixture.create_user()
    other_workspace = data_fixture.create_workspace()
    from baserow.core.teams.handler import TeamHandler

    foreign_team = TeamHandler().create_team(other_workspace, "Other")
    handler = DatabaseAccessHandler()
    scope = handler.get_scope("workspace", s.workspace.id)

    for grant in [
        {"subject_type": "user", "subject_id": outsider.id, "level": "none"},
        {"subject_type": "team", "subject_id": foreign_team.id, "level": "none"},
    ]:
        with pytest.raises(InvalidAccessSubject):
            handler.set_grants(scope, [grant])

    assert not DatabaseAccessGrant.objects.exists()


@pytest.mark.django_db
def test_inherited_grants_come_from_the_nearest_parent(access_setup):
    s = access_setup
    other_member = s.add_member()
    s.grant("none", user=s.member)
    s.grant("viewer", user=s.member, database=s.database)
    s.grant("editor", user=other_member)
    handler = DatabaseAccessHandler()

    inherited = handler.get_inherited_grants(handler.get_scope("table", s.table.id))

    assert inherited[("user", s.member.id)] == ("viewer", "database")
    assert inherited[("user", other_member.id)] == ("editor", "workspace")
    assert (
        handler.get_inherited_grants(handler.get_scope("workspace", s.workspace.id))
        == {}
    )


@pytest.mark.django_db
def test_set_grants_notifies_users_and_team_members(access_setup):
    s = access_setup
    teammate = s.add_member()
    team = s.team("Finance", teammate)
    handler = DatabaseAccessHandler()
    scope = handler.get_scope("database", s.database.id)

    with patch(
        "baserow.contrib.database.access.handler.permissions_updated.send"
    ) as send:
        handler.set_grants(
            scope,
            [
                {"subject_type": "user", "subject_id": s.member.id, "level": "none"},
                {"subject_type": "team", "subject_id": team.id, "level": "viewer"},
            ],
        )

    assert set(send.call_args.kwargs["user_ids"]) == {s.member.id, teammate.id}
