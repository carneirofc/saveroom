from datetime import datetime
from datetime import timezone as dt_timezone

import pytest

from baserow.core.scheduling.cron import (
    InvalidCron,
    compute_next_run_on,
    parse_cron,
    validate_timezone,
)


def utc(*args):
    return datetime(*args, tzinfo=dt_timezone.utc)


@pytest.mark.parametrize(
    "cron,after,expected",
    [
        # Every night at 03:00.
        ("0 3 * * *", utc(2026, 1, 1, 0, 0), utc(2026, 1, 1, 3, 0)),
        ("0 3 * * *", utc(2026, 1, 1, 3, 0), utc(2026, 1, 2, 3, 0)),
        ("0 3 * * *", utc(2026, 1, 1, 4, 0), utc(2026, 1, 2, 3, 0)),
        # Every 15 minutes.
        ("*/15 * * * *", utc(2026, 1, 1, 9, 7), utc(2026, 1, 1, 9, 15)),
        ("*/15 * * * *", utc(2026, 1, 1, 9, 45), utc(2026, 1, 1, 10, 0)),
        # Only on the first of the month.
        ("30 2 1 * *", utc(2026, 1, 5, 0, 0), utc(2026, 2, 1, 2, 30)),
        # Only on Mondays, cron counts weekdays from Sunday.
        ("0 6 * * 1", utc(2026, 1, 1, 0, 0), utc(2026, 1, 5, 6, 0)),
        # Only in June.
        ("0 0 1 6 *", utc(2026, 7, 1, 0, 0), utc(2027, 6, 1, 0, 0)),
    ],
)
def test_compute_next_run_on(cron, after, expected):
    assert compute_next_run_on(cron, "UTC", after) == expected


def test_compute_next_run_on_respects_the_timezone():
    # 03:00 in Sao Paulo (UTC-3) is 06:00 UTC.
    assert compute_next_run_on(
        "0 3 * * *", "America/Sao_Paulo", utc(2026, 1, 1, 0, 0)
    ) == utc(2026, 1, 1, 6, 0)


@pytest.mark.parametrize(
    "cron,after,expected",
    [
        # New York goes back from 02:00 EDT to 01:00 EST at 06:00 UTC on 2026-11-01,
        # so the wall-clock hour 01:00-02:00 happens twice (05:00-07:00 UTC).
        ("*/5 * * * *", utc(2026, 11, 1, 5, 30), utc(2026, 11, 1, 5, 35)),
        # Inside the repeated hour the next run must still be in the future.
        ("*/5 * * * *", utc(2026, 11, 1, 6, 30), utc(2026, 11, 1, 7, 0)),
        # A fixed time inside the repeated hour runs once, not twice.
        ("30 1 * * *", utc(2026, 11, 1, 5, 0), utc(2026, 11, 1, 5, 30)),
        ("30 1 * * *", utc(2026, 11, 1, 5, 30), utc(2026, 11, 2, 6, 30)),
        # New York skips 02:00-03:00 EST on 2026-03-08, a time in the gap runs just
        # after the jump.
        ("30 2 * * *", utc(2026, 3, 8, 6, 50), utc(2026, 3, 8, 7, 30)),
    ],
)
def test_compute_next_run_on_across_daylight_saving_changes(cron, after, expected):
    assert compute_next_run_on(cron, "America/New_York", after) == expected


def test_compute_next_run_on_is_always_in_the_future():
    moment = utc(2026, 1, 1, 3, 0)

    # Asking from exactly the due moment must move on to the next one, otherwise a
    # schedule would keep firing on the same tick forever.
    assert compute_next_run_on("0 3 * * *", "UTC", moment) > moment


@pytest.mark.parametrize(
    "cron",
    ["not a cron", "0 3 * *", "0 3 * * * *", "99 3 * * *", "0 99 * * *"],
)
def test_invalid_cron_is_rejected(cron):
    with pytest.raises(InvalidCron):
        parse_cron(cron)


def test_cron_that_never_matches_is_rejected():
    # The 31st of February does not exist.
    with pytest.raises(InvalidCron):
        compute_next_run_on("0 0 31 2 *", "UTC", utc(2026, 1, 1, 0, 0))


def test_invalid_timezone_is_rejected():
    with pytest.raises(InvalidCron):
        validate_timezone("Mars/Olympus_Mons")
