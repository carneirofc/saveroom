"""
The download endpoints exist because a link straight to the storage is unreachable
from a browser in most container deployments. These tests pin down that the link
works, that it cannot be pointed at somebody else's file, and -- the point of the
whole change -- that a file the instance lost is reported as a server side storage
problem rather than as "file not found".
"""

from datetime import timedelta
from unittest.mock import patch

from django.core.files.base import ContentFile
from django.urls import reverse
from django.utils import timezone

import pytest
from freezegun import freeze_time
from rest_framework.status import (
    HTTP_200_OK,
    HTTP_401_UNAUTHORIZED,
    HTTP_403_FORBIDDEN,
    HTTP_404_NOT_FOUND,
    HTTP_410_GONE,
    HTTP_500_INTERNAL_SERVER_ERROR,
    HTTP_503_SERVICE_UNAVAILABLE,
)

from baserow.contrib.database.export.handler import ExportHandler
from baserow.contrib.database.export.models import (
    EXPORT_JOB_FINISHED_STATUS,
    ExportJob,
)
from baserow.core.backups.handler import BackupHandler
from baserow.core.storage import StorageUnavailable, get_default_storage


def _finished_table_export(data_fixture, user):
    table = data_fixture.create_database_table(user=user)
    data_fixture.create_text_field(table=table, name="text_field")
    job = ExportJob.objects.create(
        user=user,
        table=table,
        exporter_type="csv",
        state=EXPORT_JOB_FINISHED_STATUS,
        exported_file_name="an-export.csv",
        export_options={},
    )
    storage = get_default_storage()
    storage.save(
        ExportHandler.export_file_path(job.exported_file_name),
        ContentFile(b"id,text_field\n1,hello\n"),
    )
    return job


def _download_url(api_client, token, job_id):
    response = api_client.get(
        reverse("api:database:export:get", kwargs={"job_id": job_id}),
        HTTP_AUTHORIZATION=f"JWT {token}",
    )
    return response.json()["download_url"]


@pytest.mark.django_db
def test_a_signed_link_downloads_the_table_export(
    api_client, data_fixture, use_tmp_media_root
):
    user, token = data_fixture.create_user_and_token()
    job = _finished_table_export(data_fixture, user)

    url = _download_url(api_client, token, job.id)
    assert url is not None

    # No Authorization header: the whole point is that a plain browser link works.
    response = api_client.get(url)

    assert response.status_code == HTTP_200_OK
    assert b"".join(response.streaming_content) == b"id,text_field\n1,hello\n"
    assert "attachment" in response["Content-Disposition"]


@pytest.mark.django_db
def test_the_dl_parameter_names_the_downloaded_file(
    api_client, data_fixture, use_tmp_media_root
):
    """
    The stored name is a uuid, so without this the browser would save every export
    under an unreadable name.
    """

    user, token = data_fixture.create_user_and_token()
    job = _finished_table_export(data_fixture, user)

    response = api_client.get(
        _download_url(api_client, token, job.id) + "&dl=My%20table.csv"
    )

    assert response.status_code == HTTP_200_OK
    assert "My table.csv" in response["Content-Disposition"]
    response.close()


@pytest.mark.django_db
def test_a_path_traversing_download_name_is_stripped(
    api_client, data_fixture, use_tmp_media_root
):
    user, token = data_fixture.create_user_and_token()
    job = _finished_table_export(data_fixture, user)

    response = api_client.get(
        _download_url(api_client, token, job.id) + "&dl=../../etc/passwd"
    )

    assert response.status_code == HTTP_200_OK
    assert "/" not in response["Content-Disposition"].split("filename=")[1]
    response.close()


@pytest.mark.django_db
def test_a_token_for_another_export_is_refused(
    api_client, data_fixture, use_tmp_media_root
):
    user, token = data_fixture.create_user_and_token()
    job = _finished_table_export(data_fixture, user)
    other_job = _finished_table_export(data_fixture, user)

    stolen_token = _download_url(api_client, token, other_job.id).split("token=")[1]
    url = reverse("api:database:export:download", kwargs={"job_id": job.id})

    response = api_client.get(f"{url}?token={stolen_token}")

    assert response.status_code == HTTP_401_UNAUTHORIZED
    assert response.json()["error"] == "ERROR_DOWNLOAD_TOKEN_INVALID"


@pytest.mark.django_db
def test_an_expired_token_is_refused(
    api_client, data_fixture, settings, use_tmp_media_root
):
    settings.BASEROW_EXPORT_DOWNLOAD_TOKEN_MAX_AGE_SECONDS = 600
    user, token = data_fixture.create_user_and_token()
    job = _finished_table_export(data_fixture, user)
    url = _download_url(api_client, token, job.id)

    # The download itself carries no JWT, so only the clock the signer reads moves.
    with freeze_time(timezone.now() + timedelta(minutes=10, seconds=1)):
        response = api_client.get(url)

    assert response.status_code == HTTP_401_UNAUTHORIZED
    assert response.json()["error"] == "ERROR_DOWNLOAD_TOKEN_EXPIRED"


@pytest.mark.django_db
def test_another_users_export_cannot_be_downloaded(
    api_client, data_fixture, use_tmp_media_root
):
    user, token = data_fixture.create_user_and_token()
    job = _finished_table_export(data_fixture, user)
    _, other_token = data_fixture.create_user_and_token()

    response = api_client.get(
        reverse("api:database:export:download", kwargs={"job_id": job.id}),
        HTTP_AUTHORIZATION=f"JWT {other_token}",
    )

    assert response.status_code == HTTP_404_NOT_FOUND
    assert response.json()["error"] == "ERROR_EXPORT_JOB_DOES_NOT_EXIST"


@pytest.mark.django_db
def test_an_export_past_its_expiry_says_it_expired(
    api_client, data_fixture, settings, use_tmp_media_root
):
    settings.EXPORT_FILE_EXPIRE_MINUTES = 60
    user, token = data_fixture.create_user_and_token()
    job = _finished_table_export(data_fixture, user)
    url = _download_url(api_client, token, job.id)

    ExportJob.objects.filter(id=job.id).update(
        created_at=timezone.now() - timedelta(minutes=61)
    )

    response = api_client.get(url)

    assert response.status_code == HTTP_410_GONE
    assert response.json()["error"] == "ERROR_EXPORT_FILE_EXPIRED"
    # It has to say how long exports live, otherwise "no longer available" is not
    # actionable.
    assert "60 minutes" in response.json()["detail"]


@pytest.mark.django_db
def test_a_file_lost_inside_its_retention_is_a_storage_fault(
    api_client, data_fixture, use_tmp_media_root
):
    """
    This is the bug: the export finished, the record is well inside its retention,
    and the file is not there. That is the instance losing its own file, so it must
    not be reported as a 404.
    """

    user, token = data_fixture.create_user_and_token()
    job = _finished_table_export(data_fixture, user)
    url = _download_url(api_client, token, job.id)

    get_default_storage().delete(ExportHandler.export_file_path(job.exported_file_name))

    response = api_client.get(url)

    assert response.status_code == HTTP_500_INTERNAL_SERVER_ERROR
    assert response.json()["error"] == "ERROR_EXPORT_FILE_MISSING_FROM_STORAGE"
    assert "file storage" in response.json()["detail"]
    assert "not found" not in response.json()["detail"].lower()


@pytest.mark.django_db
def test_the_storage_configuration_is_only_spelled_out_for_staff(
    api_client, data_fixture, use_tmp_media_root
):
    user, token = data_fixture.create_user_and_token()
    job = _finished_table_export(data_fixture, user)
    member_url = _download_url(api_client, token, job.id)

    staff, staff_token = data_fixture.create_user_and_token(is_staff=True)
    staff_job = _finished_table_export(data_fixture, staff)
    staff_url = _download_url(api_client, staff_token, staff_job.id)

    storage = get_default_storage()
    storage.delete(ExportHandler.export_file_path(job.exported_file_name))
    storage.delete(ExportHandler.export_file_path(staff_job.exported_file_name))

    member_detail = api_client.get(member_url).json()["detail"]
    staff_detail = api_client.get(staff_url).json()["detail"]

    assert "contact an administrator" in member_detail
    assert "MEDIA_ROOT" not in member_detail
    assert "MEDIA_ROOT" in staff_detail


@pytest.mark.django_db
def test_an_unreachable_storage_is_reported_as_unavailable(
    api_client, data_fixture, use_tmp_media_root
):
    user, token = data_fixture.create_user_and_token()
    job = _finished_table_export(data_fixture, user)
    url = _download_url(api_client, token, job.id)

    with patch(
        "baserow.core.storage.check_file_in_storage",
        side_effect=StorageUnavailable("a/path", ConnectionError("unreachable")),
    ):
        response = api_client.get(url)

    assert response.status_code == HTTP_503_SERVICE_UNAVAILABLE
    assert response.json()["error"] == "ERROR_STORAGE_UNAVAILABLE"
    # The endpoint and the path stay in the logs, never in the response.
    assert "a/path" not in response.json()["detail"]


@pytest.mark.django_db
def test_head_answers_without_a_body(api_client, data_fixture, use_tmp_media_root):
    """
    The client preflights with HEAD so a download that cannot work becomes a message
    instead of an error page where the file should have been.
    """

    user, token = data_fixture.create_user_and_token()
    job = _finished_table_export(data_fixture, user)
    url = _download_url(api_client, token, job.id)

    response = api_client.head(url)

    assert response.status_code == HTTP_200_OK
    assert response["Content-Length"] == "22"
    assert response.content == b""


@pytest.mark.django_db
def test_head_reports_a_lost_file(api_client, data_fixture, use_tmp_media_root):
    user, token = data_fixture.create_user_and_token()
    job = _finished_table_export(data_fixture, user)
    url = _download_url(api_client, token, job.id)

    get_default_storage().delete(ExportHandler.export_file_path(job.exported_file_name))

    response = api_client.head(url)

    assert response.status_code == HTTP_500_INTERNAL_SERVER_ERROR


@pytest.mark.import_export_workspace
@pytest.mark.django_db(transaction=True)
def test_a_backup_archive_downloads_through_the_api(
    api_client, data_fixture, use_tmp_media_root
):
    user, token = data_fixture.create_user_and_token()
    workspace = data_fixture.create_workspace(user=user)
    data_fixture.create_database_application(workspace=workspace)
    backup = BackupHandler().start_backup(user, workspace.id, sync=True)

    listing = api_client.get(
        reverse("api:backups:list", kwargs={"workspace_id": workspace.id}),
        HTTP_AUTHORIZATION=f"JWT {token}",
    ).json()["results"][0]

    response = api_client.get(listing["download_url"])

    assert response.status_code == HTTP_200_OK
    assert b"".join(response.streaming_content)[:2] == b"PK"
    assert (
        f"export_{backup.resource.get_archive_name()}"
        in (response["Content-Disposition"])
    )


@pytest.mark.import_export_workspace
@pytest.mark.django_db(transaction=True)
def test_a_backup_downloads_with_an_api_client_key(
    api_client, data_fixture, use_tmp_media_root
):
    user = data_fixture.create_user()
    workspace = data_fixture.create_workspace(user=user)
    data_fixture.create_database_application(workspace=workspace)
    backup = BackupHandler().start_backup(user, workspace.id, sync=True)
    _, raw_key = data_fixture.create_api_client_and_key(
        user=user, workspace=workspace, scopes=["backup.read"]
    )

    response = api_client.get(
        reverse(
            "api:backups:download",
            kwargs={
                "workspace_id": workspace.id,
                "resource_id": backup.resource_id,
            },
        ),
        HTTP_AUTHORIZATION=f"Client {raw_key}",
    )

    assert response.status_code == HTTP_200_OK
    response.close()


@pytest.mark.import_export_workspace
@pytest.mark.django_db(transaction=True)
def test_a_backup_download_needs_the_read_scope(
    api_client, data_fixture, use_tmp_media_root
):
    user = data_fixture.create_user()
    workspace = data_fixture.create_workspace(user=user)
    data_fixture.create_database_application(workspace=workspace)
    backup = BackupHandler().start_backup(user, workspace.id, sync=True)
    _, raw_key = data_fixture.create_api_client_and_key(
        user=user, workspace=workspace, scopes=["backup.write"]
    )

    response = api_client.get(
        reverse(
            "api:backups:download",
            kwargs={
                "workspace_id": workspace.id,
                "resource_id": backup.resource_id,
            },
        ),
        HTTP_AUTHORIZATION=f"Client {raw_key}",
    )

    assert response.status_code == HTTP_403_FORBIDDEN


@pytest.mark.import_export_workspace
@pytest.mark.django_db(transaction=True)
def test_a_workspace_export_archive_downloads_through_the_api(
    api_client, data_fixture, use_tmp_media_root
):
    user, token = data_fixture.create_user_and_token()
    workspace = data_fixture.create_workspace(user=user)
    data_fixture.create_database_application(workspace=workspace)
    BackupHandler().start_backup(user, workspace.id, sync=True)

    listing = api_client.get(
        reverse(
            "api:workspaces:export_workspace_list",
            kwargs={"workspace_id": workspace.id},
        ),
        HTTP_AUTHORIZATION=f"JWT {token}",
    ).json()["results"][0]

    response = api_client.get(listing["download_url"])

    assert response.status_code == HTTP_200_OK
    response.close()
