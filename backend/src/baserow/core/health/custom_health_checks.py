from datetime import datetime, timedelta, timezone

from django.conf import settings

from health_check.backends import BaseHealthCheckBackend
from health_check.exceptions import ServiceUnavailable, ServiceWarning


class DebugModeHealthCheck(BaseHealthCheckBackend):
    critical_service = False

    def check_status(self):
        if settings.DEBUG:
            raise ServiceWarning(
                "DEBUG is enabled, this is insecure for production or public usage."
            )

    def identifier(self):
        return self.__class__.__name__


class HerokuExternalFileStorageConfiguredHealthCheck(BaseHealthCheckBackend):
    critical_service = False

    def check_status(self):
        if settings.BASE_FILE_STORAGE == "django.core.files.storage.FileSystemStorage":
            raise ServiceWarning(
                "Any uploaded files will be lost on dyno restart because you have "
                "not configured an external file storage service. Please set "
                "AWS_ACCESS_KEY_ID and related env vars to prevent file loss."
            )

    def identifier(self):
        return self.__class__.__name__


class SharedFileStorageHealthCheck(BaseHealthCheckBackend):
    """
    Checks that this process and the Celery workers really see the same file storage.

    `DefaultFileStorageHealthCheck` writes and reads back inside a single process,
    which passes happily even when the web container and the worker container each
    have a volume of their own. That is the split that makes an export finish
    successfully and its download then fail with nothing to go on, so it is checked
    here instead: a worker writes a timestamp on a schedule and this reads it back.

    Only registered for a filesystem storage; object storage is shared by
    construction.
    """

    critical_service = True

    def check_status(self):
        from baserow.core.health.tasks import SHARED_STORAGE_PROBE_PATH
        from baserow.core.storage import get_default_storage

        interval = settings.BASEROW_SHARED_STORAGE_PROBE_INTERVAL_MINUTES
        # Three intervals of slack, so a single missed beat is not reported as a
        # broken deployment.
        max_age = timedelta(minutes=interval * 3)
        storage = get_default_storage()

        try:
            probe_exists = storage.exists(SHARED_STORAGE_PROBE_PATH)
        except Exception as exc:
            raise ServiceUnavailable(
                f"The file storage could not be reached: {exc}."
            ) from exc

        if not probe_exists:
            raise ServiceUnavailable(
                "No worker has written to the file storage this process can see. "
                "Either no worker is running, or the workers and the web process are "
                "using different storages, in which case exported files and backups "
                "will be created successfully but cannot be downloaded. MEDIA_ROOT "
                "must be a volume shared by both (a ReadWriteMany claim on "
                "Kubernetes), or object storage must be configured."
            )

        try:
            with storage.open(SHARED_STORAGE_PROBE_PATH, "rb") as probe:
                written_on = datetime.fromisoformat(
                    probe.read().decode("utf-8").strip()
                )
        except Exception as exc:
            raise ServiceUnavailable(
                f"The file storage probe could not be read back: {exc}."
            ) from exc

        age = datetime.now(tz=timezone.utc) - written_on

        if age > max_age:
            raise ServiceUnavailable(
                f"The last worker write this process can see is {int(age.total_seconds() // 60)} "
                f"minutes old, which is more than the {int(max_age.total_seconds() // 60)} "
                "minutes allowed. Either the workers stopped, or they no longer share "
                "a file storage with the web process, in which case exported files "
                "and backups cannot be downloaded."
            )

    def identifier(self):
        return self.__class__.__name__
