from decimal import Decimal

from django.shortcuts import reverse

import pytest
from rest_framework.status import HTTP_200_OK, HTTP_400_BAD_REQUEST

from baserow.contrib.database.action.scopes import TableActionScopeType
from baserow.contrib.database.rows.actions import ImportRowsActionType
from baserow.contrib.database.rows.exceptions import ImportAmbiguousMatches
from baserow.contrib.database.rows.handler import RowHandler
from baserow.contrib.database.rows.import_preview import TableImportPreviewHandler
from baserow.core.action.handler import ActionHandler
from baserow.test_utils.helpers import assert_undo_redo_actions_are_valid


def _create_table(data_fixture, user, rows):
    table = data_fixture.create_database_table(user=user)
    name = data_fixture.create_text_field(
        table=table, name="Name", primary=True, order=1
    )
    code = data_fixture.create_text_field(table=table, name="Code", order=2)
    qty = data_fixture.create_number_field(table=table, name="Qty", order=3)
    RowHandler().create_rows(
        user,
        table,
        rows_values=[
            {
                f"field_{name.id}": row_name,
                f"field_{code.id}": row_code,
                f"field_{qty.id}": row_qty,
            }
            for row_name, row_code, row_qty in rows
        ],
        send_realtime_update=False,
        send_webhook_events=False,
    )
    return table, name, code, qty


def _values(table, name, code, qty):
    model = table.get_model()
    return sorted(
        (
            getattr(row, f"field_{name.id}"),
            getattr(row, f"field_{code.id}"),
            getattr(row, f"field_{qty.id}"),
        )
        for row in model.objects.all()
    )


def _match_configuration(name, code, data, **kwargs):
    return {
        "upsert_fields": [name.id, code.id],
        "upsert_values": [[row[0], row[1]] for row in data],
        **kwargs,
    }


@pytest.mark.django_db
def test_import_upsert_matches_on_multiple_fields(data_fixture):
    user = data_fixture.create_user()
    table, name, code, qty = _create_table(
        data_fixture, user, [("A", "1", 1), ("A", "2", 2), ("B", "1", 3)]
    )
    data = [["A", "2", 20], ["B", "1", 3], ["C", "9", 9]]

    result = RowHandler().import_rows_with_result(
        user,
        table,
        data,
        configuration=_match_configuration(name, code, data, mode="upsert"),
        send_realtime_update=False,
    )

    assert result.error_report == {}
    assert result.summary == {
        "created": 1,
        "updated": 1,
        "unchanged": 1,
        "deleted": 0,
        "skipped": 0,
    }
    assert _values(table, name, code, qty) == [
        ("A", "1", Decimal("1")),
        ("A", "2", Decimal("20")),
        ("B", "1", Decimal("3")),
        ("C", "9", Decimal("9")),
    ]


@pytest.mark.django_db
def test_import_without_mode_and_upsert_fields_still_upserts(data_fixture):
    user = data_fixture.create_user()
    table, name, code, qty = _create_table(data_fixture, user, [("A", "1", 1)])
    data = [["A", "1", 5], ["B", "2", 6]]

    result = RowHandler().import_rows_with_result(
        user,
        table,
        data,
        configuration=_match_configuration(name, code, data),
        send_realtime_update=False,
    )

    assert result.summary["created"] == 1
    assert result.summary["updated"] == 1


@pytest.mark.django_db
def test_import_update_mode_skips_unmatched_rows(data_fixture):
    user = data_fixture.create_user()
    table, name, code, qty = _create_table(data_fixture, user, [("A", "1", 1)])
    data = [["A", "1", 5], ["B", "2", 6]]

    result = RowHandler().import_rows_with_result(
        user,
        table,
        data,
        configuration=_match_configuration(name, code, data, mode="update"),
        send_realtime_update=False,
    )

    assert result.summary["created"] == 0
    assert result.summary["updated"] == 1
    assert result.summary["skipped"] == 1
    assert _values(table, name, code, qty) == [("A", "1", Decimal("5"))]


@pytest.mark.django_db
def test_import_delete_unmatched_trashes_rows_not_in_the_file(data_fixture):
    user = data_fixture.create_user()
    table, name, code, qty = _create_table(
        data_fixture, user, [("A", "1", 1), ("B", "2", 2)]
    )
    data = [["A", "1", 1], ["C", "3", 3]]

    result = RowHandler().import_rows_with_result(
        user,
        table,
        data,
        configuration=_match_configuration(
            name, code, data, mode="upsert", delete_unmatched=True
        ),
        send_realtime_update=False,
    )

    assert result.summary["deleted"] == 1
    assert result.trashed_rows_entry_id is not None
    assert _values(table, name, code, qty) == [
        ("A", "1", Decimal("1")),
        ("C", "3", Decimal("3")),
    ]


@pytest.mark.django_db
def test_import_replace_trashes_every_existing_row(data_fixture):
    user = data_fixture.create_user()
    table, name, code, qty = _create_table(
        data_fixture, user, [("A", "1", 1), ("B", "2", 2)]
    )

    result = RowHandler().import_rows_with_result(
        user,
        table,
        [["Z", "9", 9]],
        configuration={"mode": "replace"},
        send_realtime_update=False,
    )

    assert result.summary["deleted"] == 2
    assert result.summary["created"] == 1
    assert _values(table, name, code, qty) == [("Z", "9", Decimal("9"))]


@pytest.mark.django_db
def test_import_does_not_write_unchanged_rows(data_fixture):
    user = data_fixture.create_user()
    table, name, code, qty = _create_table(data_fixture, user, [("A", "1", 1)])
    row = table.get_model().objects.get()
    data = [["A", "1", 1]]

    result = RowHandler().import_rows_with_result(
        user,
        table,
        data,
        configuration=_match_configuration(name, code, data, mode="upsert"),
        send_realtime_update=False,
    )

    assert result.summary["unchanged"] == 1
    assert result.summary["updated"] == 0
    updated_on = row.updated_on
    row.refresh_from_db()
    assert row.updated_on == updated_on


@pytest.mark.django_db
def test_import_ambiguous_matches_are_refused_unless_allowed(data_fixture):
    user = data_fixture.create_user()
    table, name, code, qty = _create_table(
        data_fixture, user, [("A", "1", 1), ("A", "1", 2)]
    )
    data = [["A", "1", 10]]

    with pytest.raises(ImportAmbiguousMatches) as exc:
        RowHandler().import_rows_with_result(
            user,
            table,
            data,
            configuration=_match_configuration(name, code, data, mode="upsert"),
            send_realtime_update=False,
        )
    assert exc.value.keys == [{"values": ["A", "1"], "file_count": 1, "table_count": 2}]
    assert _values(table, name, code, qty) == [
        ("A", "1", Decimal("1")),
        ("A", "1", Decimal("2")),
    ]

    result = RowHandler().import_rows_with_result(
        user,
        table,
        data,
        configuration=_match_configuration(
            name, code, data, mode="upsert", allow_ambiguous_matches=True
        ),
        send_realtime_update=False,
    )
    # Duplicates are paired in order: the first row is updated.
    assert result.summary["updated"] == 1
    assert _values(table, name, code, qty) == [
        ("A", "1", Decimal("2")),
        ("A", "1", Decimal("10")),
    ]


@pytest.mark.django_db
@pytest.mark.undo_redo
def test_can_undo_redo_import_updating_and_trashing_rows(data_fixture):
    session_id = "session-id"
    user = data_fixture.create_user(session_id=session_id)
    table, name, code, qty = _create_table(
        data_fixture, user, [("A", "1", 1), ("B", "2", 2)]
    )
    data = [["A", "1", 10], ["C", "3", 3]]
    scope = [TableActionScopeType.value(table_id=table.id)]

    ImportRowsActionType.do_with_result(
        user,
        table,
        data={
            "data": data,
            "configuration": _match_configuration(
                name, code, data, mode="upsert", delete_unmatched=True
            ),
        },
    )
    after_import = [
        ("A", "1", Decimal("10")),
        ("C", "3", Decimal("3")),
    ]
    assert _values(table, name, code, qty) == after_import

    action_undone = ActionHandler.undo(user, scope, session_id)
    assert_undo_redo_actions_are_valid(action_undone, [ImportRowsActionType])
    assert _values(table, name, code, qty) == [
        ("A", "1", Decimal("1")),
        ("B", "2", Decimal("2")),
    ]

    action_redone = ActionHandler.redo(user, scope, session_id)
    assert_undo_redo_actions_are_valid(action_redone, [ImportRowsActionType])
    assert _values(table, name, code, qty) == after_import


@pytest.mark.django_db
def test_import_preview_reports_changes_without_writing(data_fixture):
    user = data_fixture.create_user()
    table, name, code, qty = _create_table(
        data_fixture, user, [("A", "1", 1), ("B", "2", 2), ("B", "2", 3)]
    )
    data = [["A", "1", 5], ["C", "3", 3], ["B", "2", 2]]
    configuration = _match_configuration(
        name, code, data, mode="upsert", delete_unmatched=True
    )
    before = _values(table, name, code, qty)

    handler = TableImportPreviewHandler()
    preview = handler.preview(user, table, data, configuration=configuration)
    # The temp tables are dropped, so a second preview on the same connection works.
    second_preview = handler.preview(user, table, data, configuration=configuration)

    assert _values(table, name, code, qty) == before
    assert preview["ambiguous_blocked"] is True
    assert preview["ambiguous"] == [
        {"values": ["B", "2"], "file_count": 1, "table_count": 2}
    ]
    assert preview["summary"] == second_preview["summary"]
    assert preview["summary"]["create"] == 1
    assert preview["summary"]["update"] == 1
    assert preview["summary"]["unchanged"] == 1
    assert preview["summary"]["delete"] == 1
    assert preview["create"] == [1]
    assert preview["update"][0]["import_index"] == 0
    assert preview["update"][0]["changed_field_ids"] == [qty.id]
    assert preview["update"][0]["row"][f"field_{qty.id}"] == "1"
    assert len(preview["delete"]) == 1


@pytest.mark.django_db
def test_import_preview_endpoint(api_client, data_fixture):
    user, token = data_fixture.create_user_and_token()
    table, name, code, qty = _create_table(data_fixture, user, [("A", "1", 1)])
    url = reverse("api:database:tables:import_preview", kwargs={"table_id": table.id})
    data = [["A", "1", 2], ["B", "2", 3]]

    response = api_client.post(
        url,
        {
            "data": data,
            "configuration": _match_configuration(name, code, data, mode="upsert"),
            "sample_size": 1,
        },
        format="json",
        HTTP_AUTHORIZATION=f"JWT {token}",
    )

    assert response.status_code == HTTP_200_OK, response.json()
    response_json = response.json()
    assert response_json["summary"] == {
        "create": 1,
        "update": 1,
        "unchanged": 0,
        "delete": 0,
        "skipped": 0,
        "errors": 0,
    }
    assert response_json["create"] == [1]
    assert response_json["ambiguous_blocked"] is False

    response = api_client.post(
        url,
        {"data": data, "configuration": {"mode": "update"}},
        format="json",
        HTTP_AUTHORIZATION=f"JWT {token}",
    )
    assert response.status_code == HTTP_400_BAD_REQUEST
    assert response.json()["error"] == "ERROR_REQUEST_BODY_VALIDATION"

    response = api_client.post(
        url,
        {
            "data": data,
            "configuration": {"mode": "insert", "delete_unmatched": True},
        },
        format="json",
        HTTP_AUTHORIZATION=f"JWT {token}",
    )
    assert response.status_code == HTTP_400_BAD_REQUEST
