from django.db import connection

import pytest

from baserow.contrib.database.access.models import DatabaseAccessGrant
from baserow.core.teams.handler import TeamHandler


class AccessSetup:
    def __init__(self, data_fixture):
        self.data_fixture = data_fixture
        self.admin = data_fixture.create_user()
        self.member = data_fixture.create_user()
        self.workspace = data_fixture.create_workspace()
        data_fixture.create_user_workspace(
            workspace=self.workspace, user=self.admin, order=1
        )
        data_fixture.create_user_workspace(
            workspace=self.workspace, user=self.member, permissions="MEMBER", order=2
        )
        self.database = data_fixture.create_database_application(
            workspace=self.workspace
        )
        self.table = data_fixture.create_database_table(database=self.database)
        self.other_table = data_fixture.create_database_table(database=self.database)
        self.other_database = data_fixture.create_database_application(
            workspace=self.workspace
        )
        self.other_database_table = data_fixture.create_database_table(
            database=self.other_database
        )

    def defer_constraints(self):
        """
        `data_fixture` makes constraint checks immediate, but Django's delete
        collector doesn't order the deletion of rows referencing their parent via
        a nullable foreign key, like grants do. Restore the deferred checks
        production relies on before cascading deletes.
        """

        with connection.cursor() as cursor:
            cursor.execute("SET CONSTRAINTS ALL DEFERRED")

    def add_member(self):
        user = self.data_fixture.create_user()
        self.data_fixture.create_user_workspace(
            workspace=self.workspace, user=user, permissions="MEMBER", order=3
        )
        return user

    def team(self, name, *users):
        return TeamHandler().create_team(self.workspace, name, [u.id for u in users])

    def grant(self, level, user=None, team=None, database=None, table=None):
        return DatabaseAccessGrant.objects.create(
            workspace=self.workspace,
            user=user,
            team=team,
            database=database,
            table=table,
            level=level,
        )


@pytest.fixture
def access_setup(data_fixture):
    return AccessSetup(data_fixture)
