from datetime import datetime, timedelta
from datetime import timezone as dt_timezone

from django.urls import reverse

import pytest
from rest_framework.status import (
    HTTP_200_OK,
    HTTP_202_ACCEPTED,
    HTTP_204_NO_CONTENT,
    HTTP_400_BAD_REQUEST,
)

from baserow.core.backups.exceptions import InvalidBackupScheduleCron
from baserow.core.backups.handler import BackupHandler
from baserow.core.backups.models import BackupSchedule
from baserow.core.backups.schedule_handler import BackupScheduleHandler
from baserow.core.backups.tasks import BUSY_RETRY_DELAY, run_due_backup_schedules
from baserow.core.jobs.exceptions import MaxJobCountExceeded
from baserow.core.models import ExportApplicationsJob, ImportExportResource


def utc(*args):
    return datetime(*args, tzinfo=dt_timezone.utc)


def test_compute_next_run_on_delegates_to_the_cron_util():
    # The cron computation itself is covered in `core/scheduling/test_cron.py`.
    assert BackupScheduleHandler().compute_next_run_on(
        "0 3 * * *", "UTC", utc(2026, 1, 1, 0, 0)
    ) == utc(2026, 1, 1, 3, 0)


@pytest.mark.parametrize(
    "cron",
    ["not a cron", "0 3 * *", "0 3 * * * *", "99 3 * * *", "0 99 * * *"],
)
def test_invalid_cron_is_rejected(cron):
    with pytest.raises(InvalidBackupScheduleCron):
        BackupScheduleHandler().compute_next_run_on(cron)


def test_invalid_timezone_is_rejected():
    with pytest.raises(InvalidBackupScheduleCron):
        BackupScheduleHandler().compute_next_run_on("0 3 * * *", "Mars/Olympus_Mons")


@pytest.mark.django_db
def test_create_schedule_computes_the_next_run(api_client, data_fixture):
    user, token = data_fixture.create_user_and_token()
    workspace = data_fixture.create_workspace(user=user)

    response = api_client.post(
        reverse("api:backups:schedule_list", kwargs={"workspace_id": workspace.id}),
        {"name": "Nightly", "cron": "0 3 * * *", "keep_last": 7},
        format="json",
        HTTP_AUTHORIZATION=f"JWT {token}",
    )

    assert response.status_code == HTTP_200_OK
    response_json = response.json()
    assert response_json["cron"] == "0 3 * * *"
    assert response_json["keep_last"] == 7
    assert response_json["is_active"] is True
    assert response_json["next_run_on"] is not None


@pytest.mark.django_db
def test_create_schedule_with_an_invalid_cron(api_client, data_fixture):
    user, token = data_fixture.create_user_and_token()
    workspace = data_fixture.create_workspace(user=user)

    response = api_client.post(
        reverse("api:backups:schedule_list", kwargs={"workspace_id": workspace.id}),
        {"name": "Broken", "cron": "every night please"},
        format="json",
        HTTP_AUTHORIZATION=f"JWT {token}",
    )

    assert response.status_code == HTTP_400_BAD_REQUEST
    assert response.json()["error"] == "ERROR_INVALID_BACKUP_SCHEDULE_CRON"


@pytest.mark.django_db
def test_update_schedule_recomputes_the_next_run(api_client, data_fixture):
    user, token = data_fixture.create_user_and_token()
    workspace = data_fixture.create_workspace(user=user)
    schedule = data_fixture.create_backup_schedule(
        user=user, workspace=workspace, cron="0 3 * * *"
    )
    original_next_run = schedule.next_run_on

    response = api_client.patch(
        reverse("api:backups:schedule_item", kwargs={"schedule_id": schedule.id}),
        {"cron": "0 4 * * *"},
        format="json",
        HTTP_AUTHORIZATION=f"JWT {token}",
    )

    assert response.status_code == HTTP_200_OK
    schedule.refresh_from_db()
    assert schedule.cron == "0 4 * * *"
    assert schedule.next_run_on != original_next_run


@pytest.mark.django_db
def test_delete_schedule(api_client, data_fixture):
    user, token = data_fixture.create_user_and_token()
    workspace = data_fixture.create_workspace(user=user)
    schedule = data_fixture.create_backup_schedule(user=user, workspace=workspace)

    response = api_client.delete(
        reverse("api:backups:schedule_item", kwargs={"schedule_id": schedule.id}),
        format="json",
        HTTP_AUTHORIZATION=f"JWT {token}",
    )

    assert response.status_code == HTTP_204_NO_CONTENT
    assert not BackupSchedule.objects.filter(id=schedule.id).exists()


@pytest.mark.django_db
def test_list_schedules_of_a_workspace(api_client, data_fixture):
    user, token = data_fixture.create_user_and_token()
    workspace = data_fixture.create_workspace(user=user)
    other_workspace = data_fixture.create_workspace(user=user)
    schedule = data_fixture.create_backup_schedule(user=user, workspace=workspace)
    data_fixture.create_backup_schedule(user=user, workspace=other_workspace)

    response = api_client.get(
        reverse("api:backups:schedule_list", kwargs={"workspace_id": workspace.id}),
        format="json",
        HTTP_AUTHORIZATION=f"JWT {token}",
    )

    assert response.status_code == HTTP_200_OK
    assert [entry["id"] for entry in response.json()] == [schedule.id]


@pytest.mark.django_db
def test_schedule_of_another_workspace_is_not_readable(api_client, data_fixture):
    owner = data_fixture.create_user()
    _, outsider_token = data_fixture.create_user_and_token()
    workspace = data_fixture.create_workspace(user=owner)
    schedule = data_fixture.create_backup_schedule(user=owner, workspace=workspace)

    response = api_client.get(
        reverse("api:backups:schedule_item", kwargs={"schedule_id": schedule.id}),
        format="json",
        HTTP_AUTHORIZATION=f"JWT {outsider_token}",
    )

    assert response.status_code == HTTP_400_BAD_REQUEST
    assert response.json()["error"] == "ERROR_USER_NOT_IN_GROUP"


@pytest.mark.import_export_workspace
@pytest.mark.django_db(transaction=True)
def test_run_schedule_now(
    api_client, data_fixture, django_capture_on_commit_callbacks, use_tmp_media_root
):
    user = data_fixture.create_user()
    workspace = data_fixture.create_workspace(user=user)
    data_fixture.create_database_application(workspace=workspace)
    schedule = data_fixture.create_backup_schedule(user=user, workspace=workspace)

    with django_capture_on_commit_callbacks(execute=True):
        token = data_fixture.generate_token(user)
        response = api_client.post(
            reverse("api:backups:schedule_run", kwargs={"schedule_id": schedule.id}),
            format="json",
            HTTP_AUTHORIZATION=f"JWT {token}",
        )

    assert response.status_code == HTTP_202_ACCEPTED
    assert ExportApplicationsJob.objects.filter(workspace=workspace).count() == 1


@pytest.mark.import_export_workspace
@pytest.mark.django_db(transaction=True)
def test_periodic_task_only_runs_due_active_schedules(
    data_fixture, django_capture_on_commit_callbacks, use_tmp_media_root
):
    user = data_fixture.create_user()
    workspace = data_fixture.create_workspace(user=user)
    data_fixture.create_database_application(workspace=workspace)

    due = data_fixture.create_backup_schedule(
        user=user,
        workspace=workspace,
        next_run_on=datetime.now(dt_timezone.utc) - timedelta(minutes=1),
    )
    not_due = data_fixture.create_backup_schedule(
        user=user,
        workspace=workspace,
        next_run_on=datetime.now(dt_timezone.utc) + timedelta(days=1),
    )
    inactive = data_fixture.create_backup_schedule(
        user=user,
        workspace=workspace,
        is_active=False,
        next_run_on=datetime.now(dt_timezone.utc) - timedelta(minutes=1),
    )

    with django_capture_on_commit_callbacks(execute=True):
        run_due_backup_schedules()

    assert ExportApplicationsJob.objects.count() == 1

    due.refresh_from_db()
    not_due.refresh_from_db()
    inactive.refresh_from_db()

    assert due.last_run_on is not None
    assert due.last_error == ""
    assert due.next_run_on > datetime.now(dt_timezone.utc)
    assert not_due.last_run_on is None
    assert inactive.last_run_on is None


@pytest.mark.django_db(transaction=True)
def test_periodic_task_retries_a_schedule_whose_user_is_busy(data_fixture, monkeypatch):
    user = data_fixture.create_user()
    workspace = data_fixture.create_workspace(user=user)
    schedule = data_fixture.create_backup_schedule(
        user=user,
        workspace=workspace,
        next_run_on=datetime.now(dt_timezone.utc) - timedelta(minutes=1),
    )

    def busy(*args, **kwargs):
        raise MaxJobCountExceeded()

    monkeypatch.setattr(BackupScheduleHandler, "run_schedule", busy)
    before = datetime.now(dt_timezone.utc)
    run_due_backup_schedules()

    schedule.refresh_from_db()
    # Not skipped until tomorrow's 03:00, and not recorded as a run.
    assert schedule.next_run_on <= before + BUSY_RETRY_DELAY + timedelta(seconds=5)
    assert schedule.last_run_on is None
    assert schedule.last_error


@pytest.mark.django_db(transaction=True)
def test_periodic_task_records_a_failed_run_without_marking_it_run(
    data_fixture, monkeypatch
):
    user = data_fixture.create_user()
    workspace = data_fixture.create_workspace(user=user)
    failing = data_fixture.create_backup_schedule(
        user=user,
        workspace=workspace,
        next_run_on=datetime.now(dt_timezone.utc) - timedelta(minutes=1),
    )

    def fail(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(BackupScheduleHandler, "run_schedule", fail)
    run_due_backup_schedules()

    failing.refresh_from_db()
    assert failing.last_error == "boom"
    assert failing.last_run_on is None
    assert failing.next_run_on > datetime.now(dt_timezone.utc)


@pytest.mark.import_export_workspace
@pytest.mark.django_db(transaction=True)
def test_retention_only_considers_the_backups_of_its_schedule(
    data_fixture, django_capture_on_commit_callbacks, use_tmp_media_root
):
    user = data_fixture.create_user()
    workspace = data_fixture.create_workspace(user=user)
    data_fixture.create_database_application(workspace=workspace)
    schedule = data_fixture.create_backup_schedule(
        user=user, workspace=workspace, keep_last=1
    )
    other_schedule = data_fixture.create_backup_schedule(user=user, workspace=workspace)
    handler = BackupScheduleHandler()

    with django_capture_on_commit_callbacks(execute=True):
        manual = BackupHandler().start_backup(user, workspace.id)
        other = handler.run_schedule(other_schedule)
        handler.run_schedule(schedule)
        newest = handler.run_schedule(schedule)

    assert handler.apply_retention(schedule) == 1

    for job in (manual, other, newest):
        job.refresh_from_db()
    surviving = set(ImportExportResource.objects.values_list("id", flat=True))
    assert manual.resource_id in surviving
    assert other.resource_id in surviving
    assert newest.resource_id in surviving
    assert len(surviving) == 3


@pytest.mark.import_export_workspace
@pytest.mark.django_db(transaction=True)
def test_retention_marks_the_oldest_backups_for_deletion(
    data_fixture, django_capture_on_commit_callbacks, use_tmp_media_root
):
    user = data_fixture.create_user()
    workspace = data_fixture.create_workspace(user=user)
    data_fixture.create_database_application(workspace=workspace)
    schedule = data_fixture.create_backup_schedule(
        user=user, workspace=workspace, keep_last=1
    )

    handler = BackupScheduleHandler()

    for _ in range(2):
        with django_capture_on_commit_callbacks(execute=True):
            handler.run_schedule(schedule)

    assert ImportExportResource.objects.count() == 2

    marked = handler.apply_retention(schedule)

    assert marked == 1
    # `objects` filters out anything marked for deletion, only the newest survives.
    assert ImportExportResource.objects.count() == 1
    assert ImportExportResource.objects_and_trash.count() == 2


@pytest.mark.import_export_workspace
@pytest.mark.django_db(transaction=True)
def test_retention_does_nothing_when_it_is_not_configured(
    data_fixture, django_capture_on_commit_callbacks, use_tmp_media_root
):
    user = data_fixture.create_user()
    workspace = data_fixture.create_workspace(user=user)
    data_fixture.create_database_application(workspace=workspace)
    schedule = data_fixture.create_backup_schedule(user=user, workspace=workspace)

    handler = BackupScheduleHandler()

    for _ in range(2):
        with django_capture_on_commit_callbacks(execute=True):
            handler.run_schedule(schedule)

    assert handler.apply_retention(schedule) == 0
    assert ImportExportResource.objects.count() == 2
