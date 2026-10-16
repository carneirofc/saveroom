from datetime import date, datetime, timezone
from decimal import Decimal

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from baserow.contrib.database.data_export.parquet.types import (
    JSON_MAPPER,
    parquet_column_mapper_registry,
)
from baserow.contrib.database.data_export.parquet.writer import (
    COLUMN_NAMING_FIELD_NAME,
    TableParquetWriter,
    build_columns,
    schema_fingerprint,
)
from baserow.contrib.database.fields.registries import field_type_registry
from baserow.contrib.database.rows.handler import RowHandler
from baserow.test_utils.helpers import setup_interesting_test_table

EXTRACTED_AT = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _write(model, tmp_path, chunk_size=100, max_rows_per_file=1000, **kwargs):
    columns = build_columns(model, **kwargs)
    writer = TableParquetWriter(
        columns,
        str(tmp_path),
        run_id="run-1",
        extracted_at=EXTRACTED_AT,
        chunk_size=chunk_size,
        max_rows_per_file=max_rows_per_file,
    )
    parts = writer.write(model.objects_and_trash.all().enhance_by_fields())
    return columns, parts


def test_every_field_type_has_a_mapper_or_the_json_fallback():
    for field_type in field_type_registry.get_all():
        mapper = parquet_column_mapper_registry.get_for_field_type(field_type.type)
        assert mapper is not None
    # A type nobody registered falls back to JSON.
    assert parquet_column_mapper_registry.get_for_field_type("unknown") is JSON_MAPPER


@pytest.mark.django_db
def test_rows_are_written_with_typed_columns(data_fixture, tmp_path):
    user = data_fixture.create_user()
    table = data_fixture.create_database_table(user=user)
    other_table = data_fixture.create_database_table(database=table.database)
    other_primary = data_fixture.create_text_field(
        table=other_table, name="Name", primary=True
    )

    name = data_fixture.create_text_field(table=table, name="Name", primary=True)
    amount = data_fixture.create_number_field(
        table=table, name="Amount", number_decimal_places=2
    )
    active = data_fixture.create_boolean_field(table=table, name="Active")
    due = data_fixture.create_date_field(table=table, name="Due")
    status = data_fixture.create_single_select_field(table=table, name="Status")
    option = data_fixture.create_select_option(field=status, value="Open", color="blue")
    link = data_fixture.create_link_row_field(
        table=table, name="Link", link_row_table=other_table
    )
    secret = data_fixture.create_password_field(table=table, name="Secret")

    other_model = other_table.get_model()
    linked = other_model.objects.create(**{f"field_{other_primary.id}": "Linked"})

    handler = RowHandler()
    row = handler.create_row(
        user=user,
        table=table,
        values={
            f"field_{name.id}": "First",
            f"field_{amount.id}": "12.50",
            f"field_{active.id}": True,
            f"field_{due.id}": "2026-02-03",
            f"field_{status.id}": option.id,
            f"field_{link.id}": [linked.id],
            f"field_{secret.id}": "hunter22",
        },
    )
    deleted = handler.create_row(user=user, table=table, values={})
    handler.delete_row(user, table, deleted)

    model = table.get_model()
    columns, parts = _write(model, tmp_path)

    assert f"field_{secret.id}" not in [column.name for column in columns]
    assert [part.rows for part in parts] == [2]

    result = pq.read_table(parts[0].path)
    records = {record["id"]: record for record in result.to_pylist()}

    first = records[row.id]
    assert first[f"field_{name.id}"] == "First"
    assert first[f"field_{amount.id}"] == Decimal("12.50")
    assert first[f"field_{active.id}"] is True
    assert first[f"field_{due.id}"] == date(2026, 2, 3)
    assert first[f"field_{status.id}"] == {
        "id": option.id,
        "value": "Open",
        "color": "blue",
    }
    assert first[f"field_{link.id}"] == [{"id": linked.id, "value": "Linked"}]
    assert first["_deleted"] is False
    assert first["_run_id"] == "run-1"

    assert records[deleted.id]["_deleted"] is True

    schema_field = result.schema.field(f"field_{amount.id}")
    assert schema_field.type == pa.decimal128(38, 2)
    assert schema_field.metadata[b"baserow_field_name"] == b"Amount"


@pytest.mark.django_db
def test_every_field_type_of_an_interesting_table_is_exported(data_fixture, tmp_path):
    table, _, row, _, _ = setup_interesting_test_table(data_fixture)
    model = table.get_model()

    columns, parts = _write(model, tmp_path)

    exported_types = {column.field_type_name for column in columns}
    assert "password" not in exported_types
    assert {"text", "number", "link_row", "file", "formula"} <= exported_types

    result = pq.read_table(parts[0].path)
    assert result.num_rows == model.objects_and_trash.count()
    assert row.id in result.column("id").to_pylist()


@pytest.mark.django_db
def test_rows_roll_over_to_new_parts(data_fixture, tmp_path):
    user = data_fixture.create_user()
    table = data_fixture.create_database_table(user=user)
    data_fixture.create_text_field(table=table, name="Name", primary=True)
    RowHandler().create_rows(user, table, [{} for _ in range(5)])

    _, parts = _write(table.get_model(), tmp_path, chunk_size=2, max_rows_per_file=2)

    assert [part.rows for part in parts] == [2, 2, 1]
    assert [part.file_name for part in parts] == [
        "part-00000.parquet",
        "part-00001.parquet",
        "part-00002.parquet",
    ]
    assert sum(pq.read_table(part.path).num_rows for part in parts) == 5


@pytest.mark.django_db
def test_empty_table_still_publishes_its_schema(data_fixture, tmp_path):
    table = data_fixture.create_database_table()
    field = data_fixture.create_text_field(table=table, name="Name", primary=True)

    _, parts = _write(table.get_model(), tmp_path)

    [part] = parts
    assert part.rows == 0
    assert f"field_{field.id}" in pq.read_schema(part.path).names


@pytest.mark.django_db
def test_column_naming_and_fingerprint(data_fixture):
    table = data_fixture.create_database_table()
    field = data_fixture.create_text_field(table=table, name="Customer Name!")
    data_fixture.create_text_field(table=table, name="customer name")

    by_id = build_columns(table.get_model())
    by_name = build_columns(table.get_model(), column_naming=COLUMN_NAMING_FIELD_NAME)

    assert [column.name for column in by_name][0] == "customer_name"
    assert len({column.name for column in by_name}) == 2

    fingerprint = schema_fingerprint(by_id, "field_id")
    field.name = "Renamed"
    field.save()
    renamed = build_columns(table.get_model())

    # A rename does not change the schema when columns are named by field id.
    assert schema_fingerprint(renamed, "field_id") == fingerprint
