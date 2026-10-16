from django.urls import reverse

import pytest
from rest_framework.status import (
    HTTP_200_OK,
    HTTP_202_ACCEPTED,
    HTTP_403_FORBIDDEN,
)


def _client_header(raw_key):
    return {"HTTP_AUTHORIZATION": f"Client {raw_key}"}


@pytest.mark.django_db
def test_key_of_one_workspace_is_refused_on_another_workspace(api_client, data_fixture):
    user = data_fixture.create_user()
    workspace_one = data_fixture.create_workspace(user=user)
    workspace_two = data_fixture.create_workspace(user=user)
    _, raw_key = data_fixture.create_api_client_and_key(
        user=user, workspace=workspace_one, scopes=["backup.read", "schedule.read"]
    )

    allowed = api_client.get(
        reverse("api:backups:list", kwargs={"workspace_id": workspace_one.id}),
        **_client_header(raw_key),
    )
    refused = api_client.get(
        reverse("api:backups:list", kwargs={"workspace_id": workspace_two.id}),
        **_client_header(raw_key),
    )

    assert allowed.status_code == HTTP_200_OK
    assert refused.status_code == HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_key_of_one_workspace_is_refused_on_a_schedule_of_another(
    api_client, data_fixture
):
    user = data_fixture.create_user()
    workspace_one = data_fixture.create_workspace(user=user)
    workspace_two = data_fixture.create_workspace(user=user)
    own = data_fixture.create_backup_schedule(user=user, workspace=workspace_one)
    foreign = data_fixture.create_backup_schedule(user=user, workspace=workspace_two)
    _, raw_key = data_fixture.create_api_client_and_key(
        user=user, workspace=workspace_one, scopes=["schedule.read"]
    )

    allowed = api_client.get(
        reverse("api:backups:schedule_item", kwargs={"schedule_id": own.id}),
        **_client_header(raw_key),
    )
    refused = api_client.get(
        reverse("api:backups:schedule_item", kwargs={"schedule_id": foreign.id}),
        **_client_header(raw_key),
    )
    missing = api_client.get(
        reverse("api:backups:schedule_item", kwargs={"schedule_id": 99999}),
        **_client_header(raw_key),
    )

    assert allowed.status_code == HTTP_200_OK
    assert refused.status_code == HTTP_403_FORBIDDEN
    assert missing.status_code == HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_key_of_one_workspace_is_refused_on_a_datalake_schedule_of_another(
    api_client, data_fixture
):
    user = data_fixture.create_user()
    workspace_one = data_fixture.create_workspace(user=user)
    workspace_two = data_fixture.create_workspace(user=user)
    database = data_fixture.create_database_application(workspace=workspace_two)
    from baserow.contrib.database.data_export.models import TableExportSchedule

    schedule = TableExportSchedule.objects.create(
        name="Lake",
        workspace=workspace_two,
        database=database,
        user=user,
        destination="lake",
        cron="0 * * * *",
        next_run_on="2030-01-01T00:00:00Z",
    )
    _, raw_key = data_fixture.create_api_client_and_key(
        user=user, workspace=workspace_one, scopes=["schedule.read"]
    )

    response = api_client.get(
        reverse(
            "api:database:data_export:schedule_runs",
            kwargs={"schedule_id": schedule.id},
        ),
        **_client_header(raw_key),
    )

    assert response.status_code == HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_application_contents_are_bound_to_the_client_workspace(
    api_client, data_fixture
):
    user = data_fixture.create_user()
    workspace_one = data_fixture.create_workspace(user=user)
    workspace_two = data_fixture.create_workspace(user=user)
    own = data_fixture.create_database_application(workspace=workspace_one)
    foreign = data_fixture.create_database_application(workspace=workspace_two)
    _, raw_key = data_fixture.create_api_client_and_key(
        user=user, workspace=workspace_one, scopes=["contents.read"]
    )

    allowed = api_client.get(
        reverse("api:contents:application", kwargs={"application_id": own.id}),
        **_client_header(raw_key),
    )
    refused = api_client.get(
        reverse("api:contents:application", kwargs={"application_id": foreign.id}),
        **_client_header(raw_key),
    )

    assert allowed.status_code == HTTP_200_OK
    assert refused.status_code == HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_data_destinations_do_not_need_a_workspace(api_client, data_fixture):
    user = data_fixture.create_user()
    _, raw_key = data_fixture.create_api_client_and_key(
        user=user, scopes=["backup.read"]
    )

    response = api_client.get(
        reverse("api:data_destinations:list"), **_client_header(raw_key)
    )

    assert response.status_code == HTTP_200_OK


@pytest.mark.django_db(transaction=True)
def test_run_schedule_now_needs_both_schedule_and_backup_write(
    api_client, data_fixture, django_capture_on_commit_callbacks, use_tmp_media_root
):
    user = data_fixture.create_user()
    workspace = data_fixture.create_workspace(user=user)
    data_fixture.create_database_application(workspace=workspace)
    schedule = data_fixture.create_backup_schedule(user=user, workspace=workspace)
    url = reverse("api:backups:schedule_run", kwargs={"schedule_id": schedule.id})

    _, only_schedule = data_fixture.create_api_client_and_key(
        user=user, workspace=workspace, scopes=["schedule.write"]
    )
    _, only_backup = data_fixture.create_api_client_and_key(
        user=user, workspace=workspace, scopes=["backup.write"]
    )
    _, both = data_fixture.create_api_client_and_key(
        user=user, workspace=workspace, scopes=["schedule.write", "backup.write"]
    )

    assert (
        api_client.post(url, **_client_header(only_schedule)).status_code
        == HTTP_403_FORBIDDEN
    )
    assert (
        api_client.post(url, **_client_header(only_backup)).status_code
        == HTTP_403_FORBIDDEN
    )
    with django_capture_on_commit_callbacks(execute=True):
        response = api_client.post(url, **_client_header(both))
    assert response.status_code == HTTP_202_ACCEPTED


@pytest.mark.django_db(transaction=True)
def test_client_key_polls_its_own_backup_job(
    api_client, data_fixture, django_capture_on_commit_callbacks, use_tmp_media_root
):
    user = data_fixture.create_user()
    workspace = data_fixture.create_workspace(user=user)
    other_workspace = data_fixture.create_workspace(user=user)
    data_fixture.create_database_application(workspace=workspace)
    _, raw_key = data_fixture.create_api_client_and_key(
        user=user, workspace=workspace, scopes=["backup.read", "backup.write"]
    )
    _, other_key = data_fixture.create_api_client_and_key(
        user=user, workspace=other_workspace, scopes=["backup.read"]
    )
    _, no_scope_key = data_fixture.create_api_client_and_key(
        user=user, workspace=workspace, scopes=["schedule.read"]
    )

    with django_capture_on_commit_callbacks(execute=True):
        response = api_client.post(
            reverse("api:backups:start", kwargs={"workspace_id": workspace.id}),
            {},
            format="json",
            **_client_header(raw_key),
        )
    assert response.status_code == HTTP_202_ACCEPTED
    job_url = reverse("api:jobs:item", kwargs={"job_id": response.json()["id"]})

    polled = api_client.get(job_url, **_client_header(raw_key))
    assert polled.status_code == HTTP_200_OK
    assert polled.json()["id"] == response.json()["id"]
    assert api_client.get(job_url, **_client_header(other_key)).status_code == (
        HTTP_403_FORBIDDEN
    )
    assert api_client.get(job_url, **_client_header(no_scope_key)).status_code == (
        HTTP_403_FORBIDDEN
    )
