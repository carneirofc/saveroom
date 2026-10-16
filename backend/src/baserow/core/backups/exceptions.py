from baserow.core.exceptions import PermissionDenied
from baserow.core.scheduling.cron import InvalidCron


class BackupScheduleDoesNotExist(Exception):
    """Raised when the requested backup schedule does not exist."""


class InvalidBackupScheduleCron(InvalidCron):
    """Raised when the provided cron expression cannot be parsed."""


class RemoteBackupDoesNotExist(Exception):
    """Raised when a backup is not available on the data destination."""


class RemoteBackupCorrupted(Exception):
    """Raised when a remote archive does not match the metadata written next to it."""


class RemoteBackupTrustNotAllowed(Exception):
    """
    Raised when trusting the signing key of a remote backup is requested by a
    non-staff user, or for a destination that does not allow it.
    """


class RemoteBackupRestoreNotAllowed(Exception):
    """
    Raised when a non-staff user restores a remote backup they may not read: one made
    by another instance, or of a workspace they cannot export.
    """


class BackupScheduleNotOwned(PermissionDenied):
    """
    Raised when a user changes, deletes or runs a backup schedule that belongs to
    another member, without being an admin of its workspace.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.args = (
            "Only the owner of a backup schedule or a workspace admin can do this.",
        )
