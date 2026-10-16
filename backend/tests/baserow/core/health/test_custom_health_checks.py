from datetime import timedelta

from django.test.utils import override_settings
from django.utils import timezone

import pytest
from freezegun import freeze_time
from health_check.exceptions import ServiceUnavailable, ServiceWarning

from baserow.core.health.custom_health_checks import (
    DebugModeHealthCheck,
    HerokuExternalFileStorageConfiguredHealthCheck,
    SharedFileStorageHealthCheck,
)
from baserow.core.health.tasks import (
    is_shared_storage_probe_relevant,
    write_shared_storage_probe,
)


@override_settings(DEBUG=True)
def test_debug_health_check_raises_when_debug_true():
    with pytest.raises(ServiceWarning):
        DebugModeHealthCheck().check_status()


@override_settings(DEBUG=False)
def test_debug_health_check_does_not_raise_when_debug_false():
    DebugModeHealthCheck().check_status()


@override_settings(BASE_FILE_STORAGE="django.core.files.storage.FileSystemStorage")
def test_heroku_health_check_raises_when_default_storage_set():
    with pytest.raises(ServiceWarning):
        HerokuExternalFileStorageConfiguredHealthCheck().check_status()


@override_settings(BASE_FILE_STORAGE="storages.backends.s3boto3.S3Boto3Storage")
def test_heroku_health_check_doesnt_raise_when_boto_set():
    HerokuExternalFileStorageConfiguredHealthCheck().check_status()


@pytest.mark.django_db
def test_shared_storage_check_passes_on_a_fresh_probe(use_tmp_media_root):
    write_shared_storage_probe()

    SharedFileStorageHealthCheck().check_status()


@pytest.mark.django_db
def test_shared_storage_check_fails_when_no_worker_has_written(use_tmp_media_root):
    """
    This is what a web process looks at when the workers write their exports to a
    volume it cannot see: no probe at all, rather than a stale one.
    """

    with pytest.raises(ServiceUnavailable) as exc:
        SharedFileStorageHealthCheck().check_status()

    message = str(exc.value)
    assert "different storages" in message
    assert "ReadWriteMany" in message


@pytest.mark.django_db
def test_shared_storage_check_fails_on_a_stale_probe(settings, use_tmp_media_root):
    settings.BASEROW_SHARED_STORAGE_PROBE_INTERVAL_MINUTES = 5
    write_shared_storage_probe()

    # Three intervals of slack, so this is just past the line.
    with freeze_time(timezone.now() + timedelta(minutes=16)):
        with pytest.raises(ServiceUnavailable) as exc:
            SharedFileStorageHealthCheck().check_status()

    assert "cannot be downloaded" in str(exc.value)


@pytest.mark.django_db
def test_shared_storage_check_tolerates_a_single_missed_beat(
    settings, use_tmp_media_root
):
    settings.BASEROW_SHARED_STORAGE_PROBE_INTERVAL_MINUTES = 5
    write_shared_storage_probe()

    with freeze_time(timezone.now() + timedelta(minutes=14)):
        SharedFileStorageHealthCheck().check_status()


@override_settings(
    STORAGES={"default": {"BACKEND": "storages.backends.s3boto3.S3Boto3Storage"}}
)
def test_the_probe_is_not_relevant_for_object_storage():
    assert is_shared_storage_probe_relevant() is False


@override_settings(
    STORAGES={"default": {"BACKEND": "django.core.files.storage.FileSystemStorage"}}
)
def test_the_probe_is_relevant_for_a_filesystem_storage():
    assert is_shared_storage_probe_relevant() is True
