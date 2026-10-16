from django.shortcuts import reverse
from django.test.utils import override_settings

import pytest
from rest_framework.status import HTTP_200_OK, HTTP_401_UNAUTHORIZED, HTTP_403_FORBIDDEN


@pytest.mark.django_db
@override_settings(DEBUG=True)
def test_admin_limits_requires_staff(api_client, data_fixture):
    normal_user = data_fixture.create_user(is_staff=False)
    normal_token = data_fixture.generate_token(user=normal_user)

    response = api_client.get(
        reverse("api:admin:limits:limits"),
        format="json",
        HTTP_AUTHORIZATION=f"JWT {normal_token}",
    )
    assert response.status_code == HTTP_403_FORBIDDEN


@pytest.mark.django_db
@override_settings(DEBUG=True)
def test_admin_limits_requires_authentication(api_client):
    response = api_client.get(reverse("api:admin:limits:limits"), format="json")
    assert response.status_code == HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
@override_settings(
    DEBUG=True,
    HOURS_UNTIL_TRASH_PERMANENTLY_DELETED=72,
    EXPORT_FILE_EXPIRE_MINUTES=60,
    BASEROW_SNAPSHOT_EXPIRATION_TIME_DAYS=360,
    BASEROW_MAX_SNAPSHOTS_PER_GROUP=50,
    BASEROW_USER_LOG_ENTRY_RETENTION_DAYS=61,
    BASEROW_ROW_HISTORY_RETENTION_DAYS=180,
    BASEROW_JOB_SOFT_TIME_LIMIT=1800,
    BASEROW_JOB_EXPIRATION_TIME_LIMIT=43200,
    BASEROW_IMPORT_EXPORT_RESOURCE_REMOVAL_AFTER_DAYS=5,
)
def test_admin_limits_reports_the_configured_settings(api_client, data_fixture):
    admin_user = data_fixture.create_user(is_staff=True)
    admin_token = data_fixture.generate_token(user=admin_user)

    response = api_client.get(
        reverse("api:admin:limits:limits"),
        format="json",
        HTTP_AUTHORIZATION=f"JWT {admin_token}",
    )
    assert response.status_code == HTTP_200_OK
    assert response.json() == {
        "hours_until_trash_permanently_deleted": 72,
        "export_file_expire_minutes": 60,
        "snapshot_expiration_time_days": 360,
        "max_snapshots_per_workspace": 50,
        "user_log_entry_retention_days": 61,
        "row_history_retention_days": 180,
        "job_soft_time_limit_seconds": 1800,
        "job_expiration_time_limit_minutes": 43200,
        "import_export_resource_removal_after_days": 5,
    }


@pytest.mark.django_db
@override_settings(DEBUG=True, HOURS_UNTIL_TRASH_PERMANENTLY_DELETED=1)
def test_admin_limits_follows_a_changed_setting(api_client, data_fixture):
    admin_user = data_fixture.create_user(is_staff=True)
    admin_token = data_fixture.generate_token(user=admin_user)

    response = api_client.get(
        reverse("api:admin:limits:limits"),
        format="json",
        HTTP_AUTHORIZATION=f"JWT {admin_token}",
    )
    assert response.status_code == HTTP_200_OK
    assert response.json()["hours_until_trash_permanently_deleted"] == 1
