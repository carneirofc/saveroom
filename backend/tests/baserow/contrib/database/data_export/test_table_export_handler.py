import json
from datetime import datetime, timedelta, timezone

from django.core.management import call_command

import pyarrow.parquet as pq
import pytest
from freezegun import freeze_time

from baserow.contrib.database.data_export.handler import TableExportHandler
from baserow.contrib.database.data_export.models import (
    MODE_FULL,
    MODE_INCREMENTAL,
    RUN_STATE_FAILED,
    TableExportRun,
    TableExportSchedule,
    TableExportState,
)
from baserow.contrib.database.data_export.schedule_handler import (
    TableExportScheduleHandler,
)
from baserow.contrib.database.data_export.tasks import run_due_table_export_schedules
from baserow.contrib.database.rows.handler import RowHandler
from baserow.core.cache import local_cache
from baserow.core.data_destinations.config import parse_data_destinations_env


@pytest.fixture
def lake(settings, tmp_path):
    root = tmp_path / "lake"
    settings.BASEROW_DATA_DESTINATIONS = parse_data_destinations_env(
        json.dumps(
            [
                {
                    "name": "lake",
                    "type": "filesystem",
                    "root": str(root),
                    "purposes": ["datalake"],
                }
            ]
        )
    )
    settings.BASEROW_DATA_EXPORT_WATERMARK_OVERLAP_SECONDS = 0
    return root


def _setup(data_fixture, **schedule_kwargs):
    user = data_fixture.create_user()
    database = data_fixture.create_database_application(user=user)
    table = data_fixture.create_database_table(database=database)
    name = data_fixture.create_text_field(table=table, name="Name", primary=True)
    schedule = TableExportScheduleHandler().create_schedule(
        user,
        database,
        name="Lake",
        cron="0 * * * *",
        destination="lake",
        **schedule_kwargs,
    )
    return user, table, name, schedule


def _rows_of(lake, run):
    run_dir = lake / run.object_prefix
    records = []
    for part in sorted(run_dir.glob("part-*.parquet")):
        records.extend(pq.read_table(part).to_pylist())
    return records


@pytest.mark.django_db
def test_first_export_is_full_and_published(data_fixture, lake):
    user, table, name, schedule = _setup(data_fixture)
    RowHandler().create_rows(
        user, table, [{f"field_{name.id}": "a"}, {f"field_{name.id}": "b"}]
    )

    run = TableExportHandler().export_table(schedule, table)

    assert run.mode == MODE_FULL
    assert run.row_count == 2
    run_dir = lake / run.object_prefix
    assert (run_dir / "_SUCCESS").exists()
    manifest = json.loads((run_dir / "_manifest.json").read_text())
    assert manifest["semantics"] == "replace"
    assert manifest["table"] == {"id": table.id, "name": table.name}
    assert [column["field_id"] for column in manifest["columns"]] == [name.id]
    assert sorted(row[f"field_{name.id}"] for row in _rows_of(lake, run)) == ["a", "b"]

    latest = lake / run.object_prefix.split("/mode=")[0] / "_state" / "latest.json"
    assert json.loads(latest.read_text())["run_id"] == manifest["run_id"]

    state = TableExportState.objects.get(schedule=schedule, table=table)
    assert state.last_watermark == run.snapshot_at
    assert state.incrementals_since_full == 0


@pytest.mark.django_db
def test_incremental_export_only_holds_changed_and_deleted_rows(data_fixture, lake):
    user, table, name, schedule = _setup(data_fixture)
    handler = RowHandler()

    with freeze_time("2026-01-01 00:00"):
        unchanged, changed, deleted = handler.create_rows(
            user, table, [{}, {}, {}]
        ).created_rows
        TableExportHandler().export_table(schedule, table)

    with freeze_time("2026-01-01 01:00"):
        handler.update_rows(
            user, table, [{"id": changed.id, f"field_{name.id}": "new"}]
        )
        handler.delete_row(user, table, deleted)
        run = TableExportHandler().export_table(schedule, table)

    assert run.mode == MODE_INCREMENTAL
    records = {row["id"]: row for row in _rows_of(lake, run)}
    assert set(records) == {changed.id, deleted.id}
    assert records[changed.id][f"field_{name.id}"] == "new"
    assert records[deleted.id]["_deleted"] is True
    manifest = json.loads((lake / run.object_prefix / "_manifest.json").read_text())
    assert manifest["semantics"] == "upsert"


@pytest.mark.django_db
def test_overlap_reaches_back_before_the_previous_snapshot(
    data_fixture, lake, settings
):
    settings.BASEROW_DATA_EXPORT_WATERMARK_OVERLAP_SECONDS = 600
    user, table, name, schedule = _setup(data_fixture)

    with freeze_time("2026-01-01 00:00"):
        TableExportHandler().export_table(schedule, table)
    # Committed late, with an `updated_on` before the previous snapshot.
    with freeze_time("2026-01-01 00:00") as frozen:
        frozen.move_to("2025-12-31 23:55")
        late = RowHandler().create_row(user=user, table=table)
    with freeze_time("2026-01-01 01:00"):
        run = TableExportHandler().export_table(schedule, table)

    assert run.mode == MODE_INCREMENTAL
    assert [row["id"] for row in _rows_of(lake, run)] == [late.id]


@pytest.mark.django_db
def test_schema_change_and_full_every_n_force_a_full_export(data_fixture, lake):
    user, table, _, schedule = _setup(data_fixture, full_every_n=2)
    handler = TableExportHandler()

    with freeze_time("2026-01-01 00:00"):
        assert handler.export_table(schedule, table).mode == MODE_FULL
    with freeze_time("2026-01-01 01:00"):
        assert handler.export_table(schedule, table).mode == MODE_INCREMENTAL
    with freeze_time("2026-01-01 02:00"):
        assert handler.export_table(schedule, table).mode == MODE_INCREMENTAL
    with freeze_time("2026-01-01 03:00"):
        assert handler.export_table(schedule, table).mode == MODE_FULL

    data_fixture.create_number_field(table=table, name="Amount")
    with freeze_time("2026-01-01 04:00"):
        run = handler.export_table(schedule, table)

    assert run.mode == MODE_FULL


@pytest.mark.django_db
def test_gap_longer_than_trash_retention_forces_a_full_export(
    data_fixture, lake, settings
):
    user, table, _, schedule = _setup(data_fixture)
    handler = TableExportHandler()

    with freeze_time("2026-01-01 00:00"):
        handler.export_table(schedule, table)
    later = datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(
        hours=settings.HOURS_UNTIL_TRASH_PERMANENTLY_DELETED + 1
    )
    with freeze_time(later):
        run = handler.export_table(schedule, table)

    assert run.mode == MODE_FULL
    assert run.warnings


@pytest.mark.django_db
def test_failed_export_does_not_advance_the_watermark(data_fixture, lake, mocker):
    user, table, _, schedule = _setup(data_fixture)
    handler = TableExportHandler()
    handler.export_table(schedule, table)
    state = TableExportState.objects.get(schedule=schedule, table=table)
    watermark = state.last_watermark

    mocker.patch(
        "baserow.contrib.database.data_export.handler.TableParquetWriter.write",
        side_effect=RuntimeError("disk full"),
    )

    with pytest.raises(RuntimeError):
        handler.export_table(schedule, table)

    state.refresh_from_db()
    assert state.last_watermark == watermark
    failed = TableExportRun.objects.filter(schedule=schedule).first()
    assert failed.state == RUN_STATE_FAILED
    assert failed.error == "disk full"


@pytest.mark.django_db
def test_export_fails_when_the_user_lost_access(data_fixture, lake):
    user, table, _, schedule = _setup(data_fixture)
    table.database.workspace.workspaceuser_set.filter(user=user).delete()
    # Celery clears the local cache around every task, so a periodic run sees the
    # removed membership. Do the same here.
    local_cache.clear()
    schedule = TableExportSchedule.objects.select_related("user").get(id=schedule.id)

    runs, errors = TableExportHandler().export_schedule(schedule)

    assert runs == []
    assert len(errors) == 1


@pytest.mark.django_db(transaction=True)
def test_periodic_task_runs_due_schedules(
    data_fixture, lake, django_capture_on_commit_callbacks
):
    user, table, _, schedule = _setup(data_fixture)
    TableExportSchedule.objects.filter(id=schedule.id).update(
        next_run_on=datetime.now(timezone.utc) - timedelta(minutes=1)
    )

    with django_capture_on_commit_callbacks(execute=True):
        run_due_table_export_schedules()

    schedule.refresh_from_db()
    assert schedule.next_run_on > datetime.now(timezone.utc)
    assert schedule.last_error == ""
    assert TableExportRun.objects.filter(schedule=schedule).count() == 1


@pytest.mark.django_db
def test_export_table_parquet_command(data_fixture, lake):
    user, table, _, schedule = _setup(data_fixture, is_active=False)
    RowHandler().create_row(user=user, table=table)

    call_command(
        "export_table_parquet", "--schedule-id", str(schedule.id), "--mode", "full"
    )

    [run] = TableExportRun.objects.filter(schedule=schedule)
    assert run.row_count == 1
    assert (lake / run.object_prefix / "_SUCCESS").exists()
