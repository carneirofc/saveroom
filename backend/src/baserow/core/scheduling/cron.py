"""
Cron expression helpers shared by every schedule that runs on a five field crontab,
such as backup schedules and table export schedules.
"""

from datetime import datetime, timedelta
from typing import Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.utils import timezone

from celery.schedules import crontab

# A cron expression that never matches within four years is treated as invalid rather
# than looping forever. Four years covers the leap year cycle.
MAX_DAYS_LOOKAHEAD = 366 * 4


class InvalidCron(Exception):
    """Raised when a cron expression or its timezone cannot be used."""


def parse_cron(expression: str) -> crontab:
    """
    Turns a five field cron expression into a celery crontab schedule.

    :param expression: A `minute hour day_of_month month day_of_week` expression.
    :raises InvalidCron: When the expression cannot be parsed.
    :return: The parsed schedule.
    """

    fields = expression.split()

    if len(fields) != 5:
        raise InvalidCron(
            "A cron expression must have exactly five fields: minute, hour, "
            "day_of_month, month_of_year and day_of_week."
        )

    minute, hour, day_of_month, month_of_year, day_of_week = fields

    try:
        # `crontab` expands every field into a set of allowed values in its
        # constructor, so an invalid expression is rejected here instead of at run
        # time.
        return crontab(
            minute=minute,
            hour=hour,
            day_of_month=day_of_month,
            month_of_year=month_of_year,
            day_of_week=day_of_week,
        )
    except (ValueError, KeyError) as exc:
        raise InvalidCron(f"The cron expression '{expression}' is invalid: {exc}")


def validate_timezone(name: str) -> str:
    """
    Checks that the given timezone name is known.

    :param name: An IANA timezone name.
    :raises InvalidCron: When the timezone is unknown.
    :return: The validated name.
    """

    try:
        ZoneInfo(name)
    except ZoneInfoNotFoundError, ValueError:
        raise InvalidCron(f"The timezone '{name}' is not known.")

    return name


def compute_next_run_on(
    cron: str,
    tz_name: str = "UTC",
    after: Optional[datetime] = None,
) -> datetime:
    """
    Computes the first moment the cron expression is due after the given moment.

    :param cron: The cron expression.
    :param tz_name: The timezone the expression is evaluated in.
    :param after: The moment to start from, defaults to now. The returned moment is
        always strictly after it.
    :raises InvalidCron: When the expression or timezone is invalid, or the expression
        never matches.
    :return: The next due moment, as an aware UTC datetime.
    """

    schedule = parse_cron(cron)
    tz = ZoneInfo(validate_timezone(tz_name))
    utc = ZoneInfo("UTC")
    after = (after or timezone.now()).astimezone(utc)

    hours = sorted(schedule.hour)
    minutes = sorted(schedule.minute)

    # Start looking from the next whole minute so the result is never the moment we
    # were asked to look after.
    candidate = after.astimezone(tz).replace(second=0, microsecond=0) + timedelta(
        minutes=1
    )

    for day in range(MAX_DAYS_LOOKAHEAD):
        if _day_matches(schedule, candidate):
            for hour in hours:
                if hour < candidate.hour:
                    continue
                for minute in minutes:
                    if hour == candidate.hour and minute < candidate.minute:
                        continue
                    # Wall-clock times are matched on their first occurrence: a time
                    # repeated when the clocks go back is due once, and a time skipped
                    # when they go forward resolves to the moment just after the jump.
                    # Comparing in UTC keeps the result strictly after `after`, also
                    # when `after` falls in the repeated hour.
                    found = candidate.replace(hour=hour, minute=minute, fold=0)
                    found = found.astimezone(utc)
                    if found > after:
                        return found

        candidate = (candidate + timedelta(days=1)).replace(hour=0, minute=0)

    raise InvalidCron(
        f"The cron expression '{cron}' does not match any moment within "
        f"{MAX_DAYS_LOOKAHEAD} days."
    )


def _day_matches(schedule: crontab, moment: datetime) -> bool:
    """
    Whether the date part of the given moment satisfies the schedule.

    Both `day_of_month` and `day_of_week` must match. Note that this is stricter than
    the OR semantics of some cron implementations, and matches how celery itself
    evaluates a crontab.
    """

    # Python counts weekdays from Monday, cron counts them from Sunday.
    cron_weekday = (moment.weekday() + 1) % 7

    return (
        moment.month in schedule.month_of_year
        and moment.day in schedule.day_of_month
        and cron_weekday in schedule.day_of_week
    )
