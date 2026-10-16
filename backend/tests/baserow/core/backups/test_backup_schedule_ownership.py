from datetime import datetime, timedelta
from datetime import timezone as dt_timezone

from django.urls import reverse

import pytest
from rest_framework.status import (
    HTTP_200_OK,
    HTTP_204_NO_CONTENT,
    HTTP_403_FORBIDDEN,
    HTTP_404_NOT_FOUND,
)

from baserow.core.backups.exceptions import BackupScheduleNotOwned
from baserow.core.backups.models import BackupSchedule
from baserow.core.backups.schedule_handler import BackupScheduleHandler
from baserow.core.backups.tasks import run_due_backup_schedules
from baserow.core.exceptions import ApplicationDoesNotExist
from baserow.core.models import ExportApplicationsJob


def _setup(data_fixture):
    owner = data_fixture.create_user()
    other = data_fixture.create_user()
    admin = data_fixture.create_user()
    workspace = data_fixture.create_workspace(
        user=owner, members=[other], custom_permissions=[(admin, "ADMIN")]
    )
    schedule = data_fixture.create_backup_schedule(user=owner, workspace=workspace)
    return owner, other, admin, workspace, schedule


@pytest.mark.django_db
def test_member_cannot_update_delete_or_run_a_schedule_of_another_member(
    api_client, data_fixture
):
    # `owner` is a plain member here: only `admin` has the admin role.
    owner = data_fixture.create_user()
    other = data_fixture.create_user()
    admin = data_fixture.create_user()
    workspace = data_fixture.create_workspace(
        members=[owner, other], custom_permissions=[(admin, "ADMIN")]
    )
    schedule = data_fixture.create_backup_schedule(user=owner, workspace=workspace)
    token = data_fixture.generate_token(other)
    item_url = reverse("api:backups:schedule_item", kwargs={"schedule_id": schedule.id})
    run_url = reverse("api:backups:schedule_run", kwargs={"schedule_id": schedule.id})

    response = api_client.patch(
        item_url, {"name": "Hijacked"}, format="json", HTTP_AUTHORIZATION=f"JWT {token}"
    )
    assert response.status_code == HTTP_403_FORBIDDEN
    assert response.json()["error"] == "ERROR_BACKUP_SCHEDULE_NOT_OWNED"

    response = api_client.delete(item_url, HTTP_AUTHORIZATION=f"JWT {token}")
    assert response.status_code == HTTP_403_FORBIDDEN

    response = api_client.post(run_url, HTTP_AUTHORIZATION=f"JWT {token}")
    assert response.status_code == HTTP_403_FORBIDDEN

    schedule.refresh_from_db()
    assert schedule.name != "Hijacked"
    assert not ExportApplicationsJob.objects.exists()


@pytest.mark.django_db
def test_owner_and_workspace_admin_can_manage_a_schedule(api_client, data_fixture):
    owner = data_fixture.create_user()
    admin = data_fixture.create_user()
    workspace = data_fixture.create_workspace(
        members=[owner], custom_permissions=[(admin, "ADMIN")]
    )
    schedule = data_fixture.create_backup_schedule(user=owner, workspace=workspace)
    item_url = reverse("api:backups:schedule_item", kwargs={"schedule_id": schedule.id})

    for user in (owner, admin):
        token = data_fixture.generate_token(user)
        response = api_client.patch(
            item_url,
            {"name": f"By {user.id}"},
            format="json",
            HTTP_AUTHORIZATION=f"JWT {token}",
        )
        assert response.status_code == HTTP_200_OK

    token = data_fixture.generate_token(admin)
    response = api_client.delete(item_url, HTTP_AUTHORIZATION=f"JWT {token}")
    assert response.status_code == HTTP_204_NO_CONTENT


@pytest.mark.django_db
def test_staff_can_manage_a_schedule_of_a_workspace_they_are_not_in(data_fixture):
    owner, _, _, _, schedule = _setup(data_fixture)
    staff = data_fixture.create_user(is_staff=True)

    updated = BackupScheduleHandler().update_schedule(staff, schedule, name="Staff")

    assert updated.name == "Staff"
    BackupScheduleHandler().delete_schedule(staff, updated)
    assert not BackupSchedule.objects.filter(id=schedule.id).exists()


@pytest.mark.import_export_workspace
@pytest.mark.django_db(transaction=True)
def test_run_schedule_handler_requires_owner_or_admin(data_fixture, use_tmp_media_root):
    owner = data_fixture.create_user()
    other = data_fixture.create_user()
    workspace = data_fixture.create_workspace(members=[owner, other])
    data_fixture.create_database_application(workspace=workspace)
    schedule = data_fixture.create_backup_schedule(user=owner, workspace=workspace)

    with pytest.raises(BackupScheduleNotOwned):
        BackupScheduleHandler().run_schedule(schedule, requested_by=other)

    job = BackupScheduleHandler().run_schedule(schedule, requested_by=owner)
    assert job.user_id == owner.id


@pytest.mark.django_db
def test_application_ids_must_belong_to_the_workspace(data_fixture):
    user = data_fixture.create_user()
    workspace = data_fixture.create_workspace(user=user)
    own = data_fixture.create_database_application(workspace=workspace)
    foreign = data_fixture.create_database_application()
    handler = BackupScheduleHandler()

    schedule = handler.create_schedule(
        user, workspace, name="Ok", cron="0 3 * * *", application_ids=[own.id]
    )
    assert schedule.application_ids == [own.id]

    with pytest.raises(ApplicationDoesNotExist):
        handler.create_schedule(
            user, workspace, name="Bad", cron="0 3 * * *", application_ids=[foreign.id]
        )

    with pytest.raises(ApplicationDoesNotExist):
        handler.update_schedule(user, schedule, application_ids=[own.id, 99999])


@pytest.mark.django_db
def test_application_ids_outside_the_workspace_are_rejected_by_the_api(
    api_client, data_fixture
):
    user, token = data_fixture.create_user_and_token()
    workspace = data_fixture.create_workspace(user=user)
    foreign = data_fixture.create_database_application()

    response = api_client.post(
        reverse("api:backups:schedule_list", kwargs={"workspace_id": workspace.id}),
        {"name": "Bad", "cron": "0 3 * * *", "application_ids": [foreign.id]},
        format="json",
        HTTP_AUTHORIZATION=f"JWT {token}",
    )

    assert response.status_code == HTTP_404_NOT_FOUND
    assert not BackupSchedule.objects.exists()


@pytest.mark.import_export_workspace
@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("reason", ["inactive", "to_be_deleted"])
def test_periodic_task_disables_a_schedule_of_an_inactive_owner(
    data_fixture, django_capture_on_commit_callbacks, use_tmp_media_root, reason
):
    owner = data_fixture.create_user()
    workspace = data_fixture.create_workspace(user=owner)
    data_fixture.create_database_application(workspace=workspace)
    schedule = data_fixture.create_backup_schedule(
        user=owner,
        workspace=workspace,
        next_run_on=datetime.now(dt_timezone.utc) - timedelta(minutes=1),
    )

    if reason == "inactive":
        owner.is_active = False
        owner.save()
    else:
        owner.profile.to_be_deleted = True
        owner.profile.save()

    with django_capture_on_commit_callbacks(execute=True):
        run_due_backup_schedules()

    schedule.refresh_from_db()
    assert schedule.is_active is False
    assert schedule.last_error
    assert schedule.last_run_on is None
    assert not ExportApplicationsJob.objects.exists()
