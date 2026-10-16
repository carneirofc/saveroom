from datetime import datetime, timedelta, timezone
from os.path import join

from django.conf import settings
from django.core.files.base import ContentFile

from loguru import logger

from baserow.config.celery import app
from baserow.core.storage import OverwritingStorageHandler

# Written by a worker, read by the web process. The name is stable so the probe never
# accumulates, and it lives next to the exports because that is the directory whose
# reachability actually decides whether a download works.
SHARED_STORAGE_PROBE_PATH = join(
    settings.EXPORT_FILES_DIRECTORY, ".shared_storage_probe"
)


def is_shared_storage_probe_relevant() -> bool:
    """
    The probe only makes sense for a filesystem storage. Object storage is shared by
    construction: every process talks to the same bucket, so there is nothing for the
    probe to prove.
    """

    return (
        settings.STORAGES["default"]["BACKEND"]
        == "django.core.files.storage.FileSystemStorage"
    )


@app.task(bind=True, queue="export")
def write_shared_storage_probe(self):
    """
    Writes a timestamp into the export directory from a worker.

    Exports and backups are produced by workers and downloaded through the web
    process. When those two do not share a filesystem, an export finishes perfectly
    and its download then fails, which is impossible to diagnose from either side
    alone. The web process reads this file back in `SharedFileStorageHealthCheck`, so
    the split is reported before anyone runs an export.
    """

    if not is_shared_storage_probe_relevant():
        return

    now = datetime.now(tz=timezone.utc).isoformat()

    try:
        OverwritingStorageHandler().save(
            SHARED_STORAGE_PROBE_PATH, ContentFile(now.encode("utf-8"))
        )
    except Exception:
        logger.exception(
            "Could not write the shared storage probe to {}.",
            SHARED_STORAGE_PROBE_PATH,
        )
        raise


@app.on_after_finalize.connect
def setup_periodic_tasks(sender, **kwargs):
    sender.add_periodic_task(
        timedelta(minutes=settings.BASEROW_SHARED_STORAGE_PROBE_INTERVAL_MINUTES),
        write_shared_storage_probe.s(),
    )
