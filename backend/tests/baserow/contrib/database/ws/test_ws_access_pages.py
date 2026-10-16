import pytest

from baserow.contrib.database.access.models import DatabaseAccessGrant
from baserow.ws.registries import page_registry


@pytest.mark.django_db
@pytest.mark.websockets
def test_table_page_subscription_honours_access_levels(data_fixture):
    table_page = page_registry.get("table")
    workspace = data_fixture.create_workspace()
    member = data_fixture.create_user()
    data_fixture.create_user_workspace(
        workspace=workspace, user=member, permissions="MEMBER"
    )
    database = data_fixture.create_database_application(workspace=workspace)
    table = data_fixture.create_database_table(database=database)
    other_table = data_fixture.create_database_table(database=database)

    assert table_page.can_add(member, "ws-1", table.id) is True

    DatabaseAccessGrant.objects.create(
        workspace=workspace, database=database, user=member, level="none"
    )
    assert table_page.can_add(member, "ws-1", table.id) is False

    DatabaseAccessGrant.objects.create(
        workspace=workspace, table=table, user=member, level="viewer"
    )
    assert table_page.can_add(member, "ws-1", table.id) is True
    assert table_page.can_add(member, "ws-1", other_table.id) is False
