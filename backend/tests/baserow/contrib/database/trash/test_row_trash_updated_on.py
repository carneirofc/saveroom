from datetime import datetime, timezone

import pytest
from freezegun import freeze_time

from baserow.contrib.database.rows.handler import RowHandler
from baserow.contrib.database.trash.models import TrashedRows
from baserow.core.trash.handler import TrashHandler


def utc(*args):
    return datetime(*args, tzinfo=timezone.utc)


@pytest.mark.django_db
def test_trashing_and_restoring_a_row_bumps_updated_on(data_fixture):
    user = data_fixture.create_user()
    table = data_fixture.create_database_table(user=user)
    data_fixture.create_text_field(table=table, name="Name", primary=True)

    with freeze_time("2026-01-01 00:00"):
        row = RowHandler().create_row(user=user, table=table)

    with freeze_time("2026-01-02 00:00"):
        RowHandler().delete_row(user, table, row)

    model = table.get_model()
    assert model.trash.get(id=row.id).updated_on == utc(2026, 1, 2)

    with freeze_time("2026-01-03 00:00"):
        TrashHandler.restore_item(user, "row", row.id, parent_trash_item_id=table.id)

    assert model.objects.get(id=row.id).updated_on == utc(2026, 1, 3)


@pytest.mark.django_db
def test_trashing_and_restoring_rows_in_bulk_bumps_updated_on(data_fixture):
    user = data_fixture.create_user()
    table = data_fixture.create_database_table(user=user)
    data_fixture.create_text_field(table=table, name="Name", primary=True)

    with freeze_time("2026-01-01 00:00"):
        rows = RowHandler().create_rows(user, table, [{}, {}]).created_rows
    row_ids = [row.id for row in rows]

    with freeze_time("2026-01-02 00:00"):
        RowHandler().delete_rows(user, table, row_ids)

    model = table.get_model()
    assert {row.updated_on for row in model.trash.filter(id__in=row_ids)} == {
        utc(2026, 1, 2)
    }

    trashed_rows = TrashedRows.objects.get(table=table)
    with freeze_time("2026-01-03 00:00"):
        TrashHandler.restore_item(
            user, "rows", trashed_rows.id, parent_trash_item_id=table.id
        )

    assert {row.updated_on for row in model.objects.filter(id__in=row_ids)} == {
        utc(2026, 1, 3)
    }
