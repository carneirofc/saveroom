from django.conf import settings
from django.db import transaction
from django.utils import timezone

from loguru import logger

from baserow.config.celery import app


@app.task(bind=True, queue="export")
def run_due_table_export_schedules(self):
    """
    Queues an export for every active schedule that is due and moves its
    `next_run_on` forward. Each schedule is locked with `skip_locked`, so concurrent
    ticks never queue the same schedule twice.
    """

    from .models import TableExportSchedule
    from .schedule_handler import TableExportScheduleHandler

    handler = TableExportScheduleHandler()
    now = timezone.now()

    due_ids = list(
        TableExportSchedule.objects.filter(
            is_active=True, next_run_on__lte=now
        ).values_list("id", flat=True)
    )

    for schedule_id in due_ids:
        with transaction.atomic():
            schedule = (
                TableExportSchedule.objects.select_for_update(
                    skip_locked=True, of=("self",)
                )
                .filter(id=schedule_id, is_active=True, next_run_on__lte=now)
                .select_related("user")
                .first()
            )

            if schedule is None:
                continue

            owner = schedule.user
            profile = getattr(owner, "profile", None)
            if not owner.is_active or (profile and profile.to_be_deleted):
                # The export would run as a user who can no longer sign in.
                schedule.is_active = False
                schedule.last_error = (
                    "Disabled because the owner of the schedule is no longer active."
                )
                schedule.save(update_fields=["is_active", "last_error", "updated_on"])
                continue

            try:
                schedule.next_run_on = handler.compute_next_run_on(
                    schedule.cron, schedule.timezone, after=now
                )
            except Exception as exc:  # noqa: BLE001 - recorded, never fatal
                schedule.is_active = False
                schedule.last_error = str(exc)
                schedule.save(update_fields=["is_active", "last_error", "updated_on"])
                continue

            schedule.last_run_on = now
            schedule.save(update_fields=["next_run_on", "last_run_on", "updated_on"])
            transaction.on_commit(
                lambda schedule_id=schedule_id: run_table_export_schedule.delay(
                    schedule_id
                )
            )


@app.task(
    bind=True,
    queue="export",
    soft_time_limit=settings.BASEROW_DATA_EXPORT_SOFT_TIME_LIMIT,
)
def run_table_export_schedule(self, schedule_id: int, mode: str = "auto"):
    """
    Exports every table of a schedule and records the errors of the failed tables on
    the schedule.
    """

    from .handler import TableExportHandler
    from .models import TableExportSchedule

    schedule = (
        TableExportSchedule.objects.filter(id=schedule_id)
        .select_related("workspace", "database", "user")
        .first()
    )
    if schedule is None:
        return

    _, errors = TableExportHandler().export_schedule(schedule, mode)

    if errors:
        logger.error(
            "Table export schedule {schedule_id} had failures: {errors}",
            schedule_id=schedule_id,
            errors=errors,
        )

    schedule.last_error = "\n".join(errors)
    schedule.save(update_fields=["last_error", "updated_on"])


@app.on_after_finalize.connect
def setup_periodic_tasks(sender, **kwargs):
    sender.add_periodic_task(
        settings.BASEROW_TABLE_EXPORT_SCHEDULE_TICK_CRONTAB,
        run_due_table_export_schedules.s(),
    )
