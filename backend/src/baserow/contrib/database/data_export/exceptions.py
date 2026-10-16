from baserow.core.scheduling.cron import InvalidCron


class TableExportScheduleDoesNotExist(Exception):
    """Raised when the requested table export schedule does not exist."""


class InvalidTableExportScheduleCron(InvalidCron):
    """Raised when the cron expression or timezone of a schedule cannot be used."""


class TableExportTablesNotInDatabase(Exception):
    """Raised when a schedule targets tables that are not in its database."""


class TableExportAlreadyRunning(Exception):
    """Raised when another export of the same schedule and table is in progress."""
