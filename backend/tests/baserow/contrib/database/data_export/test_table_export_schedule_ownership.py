from datetime import datetime, timedelta
from datetime import timezone as dt_timezone

import pytest

from baserow.contrib.database.data_export import tasks
from baserow.contrib.database.data_export.models import TableExportSchedule
from baserow.contrib.database.data_export.schedule_handler import (
    TableExportScheduleHandler,
)
from baserow.core.exceptions import PermissionDenied


def _schedule(data_fixture, user, workspace, **kwargs):
    database = data_fixture.create_database_application(workspace=workspace)
    return TableExportSchedule.objects.create(
        name="Lake",
        workspace=workspace,
        database=database,
        user=user,
        destination="lake",
        cron="0 * * * *",
        next_run_on=datetime.now(dt_timezone.utc) - timedelta(minutes=1),
        **kwargs,
    )


@pytest.mark.django_db(transaction=True)
def test_run_by_another_member_does_not_queue_an_export(data_fixture, monkeypatch):
    owner = data_fixture.create_user()
    other = data_fixture.create_user()
    admin = data_fixture.create_user()
    workspace = data_fixture.create_workspace(
        members=[owner, other], custom_permissions=[(admin, "ADMIN")]
    )
    schedule = _schedule(data_fixture, owner, workspace)
    queued = []
    monkeypatch.setattr(
        tasks.run_table_export_schedule,
        "delay",
        lambda schedule_id, mode="auto": queued.append(schedule_id),
    )

    with pytest.raises(PermissionDenied):
        TableExportScheduleHandler().run_schedule(other, schedule)
    assert queued == []

    TableExportScheduleHandler().run_schedule(owner, schedule)
    TableExportScheduleHandler().run_schedule(admin, schedule)
    assert queued == [schedule.id, schedule.id]


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("reason", ["inactive", "to_be_deleted"])
def test_periodic_task_disables_a_schedule_of_an_inactive_owner(
    data_fixture, monkeypatch, reason
):
    owner = data_fixture.create_user()
    workspace = data_fixture.create_workspace(user=owner)
    schedule = _schedule(data_fixture, owner, workspace)
    queued = []
    monkeypatch.setattr(
        tasks.run_table_export_schedule,
        "delay",
        lambda schedule_id, mode="auto": queued.append(schedule_id),
    )

    if reason == "inactive":
        owner.is_active = False
        owner.save()
    else:
        owner.profile.to_be_deleted = True
        owner.profile.save()

    tasks.run_due_table_export_schedules()

    schedule.refresh_from_db()
    assert schedule.is_active is False
    assert schedule.last_error
    assert queued == []
