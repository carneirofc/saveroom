from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from loguru import logger

from baserow.config.celery import app

# How soon a schedule is retried when its user still has a backup running.
BUSY_RETRY_DELAY = timedelta(minutes=5)


@app.task(bind=True, queue="export")
def run_due_backup_schedules(self):
    """
    Starts a backup for every active schedule that is due, and moves its `next_run_on`
    forward.

    Each schedule is locked individually with `skip_locked`, so a schedule is never
    started twice when several workers tick at the same time and a slow schedule does
    not hold up the others.

    A run that cannot start because the user still has a backup running, for example
    the previous run of a frequent schedule, is retried after `BUSY_RETRY_DELAY`
    instead of being skipped until the next cron match.
    """

    from baserow.core.backups.models import BackupSchedule
    from baserow.core.backups.schedule_handler import BackupScheduleHandler
    from baserow.core.jobs.exceptions import MaxJobCountExceeded

    handler = BackupScheduleHandler()
    now = timezone.now()

    due_ids = list(
        BackupSchedule.objects.filter(is_active=True, next_run_on__lte=now).values_list(
            "id", flat=True
        )
    )

    for schedule_id in due_ids:
        with transaction.atomic():
            schedule = (
                BackupSchedule.objects.select_for_update(skip_locked=True, of=("self",))
                .filter(id=schedule_id, is_active=True, next_run_on__lte=now)
                .select_related("workspace", "user")
                .first()
            )

            if schedule is None:
                # Another worker picked it up, or it stopped being due.
                continue

            owner = schedule.user
            profile = getattr(owner, "profile", None)
            if not owner.is_active or (profile and profile.to_be_deleted):
                # The backup would run as a user who can no longer sign in.
                schedule.is_active = False
                schedule.last_error = (
                    "Disabled because the owner of the schedule is no longer active."
                )
                schedule.save(update_fields=["is_active", "last_error", "updated_on"])
                continue

            next_run_on = handler.compute_next_run_on(
                schedule.cron, schedule.timezone, after=now
            )

            try:
                # A savepoint, so a database error in the run leaves the transaction
                # holding the lock usable for recording the failure.
                with transaction.atomic():
                    handler.run_schedule(schedule)
                schedule.last_error = ""
                schedule.last_run_on = now
            except MaxJobCountExceeded:
                logger.info(
                    "Backup schedule {schedule_id} postponed, its user still has a "
                    "backup running.",
                    schedule_id=schedule.id,
                )
                schedule.last_error = (
                    "Postponed because a backup of this user was still running."
                )
                next_run_on = min(next_run_on, now + BUSY_RETRY_DELAY)
            except Exception as exc:  # noqa: BLE001 - recorded, never fatal
                logger.error(
                    "Backup schedule {schedule_id} failed: {error}",
                    schedule_id=schedule.id,
                    error=exc,
                )
                schedule.last_error = str(exc)

            schedule.next_run_on = next_run_on
            schedule.save(
                update_fields=["last_error", "last_run_on", "next_run_on", "updated_on"]
            )

        # Retention is applied outside the lock: it only marks older resources for
        # deletion and must not keep the schedule row locked while it does so.
        apply_backup_retention.delay(schedule_id)


@app.task(bind=True, queue="export")
def apply_backup_retention(self, schedule_id: int):
    """
    Marks the backups of a schedule that fall outside its retention window for
    deletion.

    :param schedule_id: The id of the schedule whose retention rules are applied.
    """

    from baserow.core.backups.destination import BackupDestinationHandler
    from baserow.core.backups.models import BackupSchedule
    from baserow.core.backups.schedule_handler import BackupScheduleHandler

    schedule = (
        BackupSchedule.objects.filter(id=schedule_id)
        .select_related("workspace", "user")
        .first()
    )

    if schedule is None:
        return

    BackupScheduleHandler().apply_retention(schedule)

    try:
        BackupDestinationHandler().apply_remote_retention(schedule)
    except Exception as exc:  # noqa: BLE001 - an unreachable destination must not
        # break the local retention, the next run tries again.
        logger.error(
            "Remote retention of backup schedule {schedule_id} failed: {error}",
            schedule_id=schedule_id,
            error=exc,
        )


@app.on_after_finalize.connect
def setup_periodic_tasks(sender, **kwargs):
    sender.add_periodic_task(
        settings.BASEROW_BACKUP_SCHEDULE_TICK_CRONTAB,
        run_due_backup_schedules.s(),
    )
