"""
The scopes that can be granted to an API client.

A scope never widens what a client can do: the client always acts as the user that
created it, so the regular permission manager checks still apply. A scope only narrows
that user's permissions down to the endpoints the integration actually needs.
"""

SCOPE_BACKUP_READ = "backup.read"
SCOPE_BACKUP_WRITE = "backup.write"
SCOPE_BACKUP_RESTORE = "backup.restore"
SCOPE_CONTENTS_READ = "contents.read"
SCOPE_SCHEDULE_READ = "schedule.read"
SCOPE_SCHEDULE_WRITE = "schedule.write"

ALL_SCOPES = [
    SCOPE_BACKUP_READ,
    SCOPE_BACKUP_WRITE,
    SCOPE_BACKUP_RESTORE,
    SCOPE_CONTENTS_READ,
    SCOPE_SCHEDULE_READ,
    SCOPE_SCHEDULE_WRITE,
]

SCOPE_DESCRIPTIONS = {
    SCOPE_BACKUP_READ: "List backups and obtain their download URL.",
    SCOPE_BACKUP_WRITE: "Start new backups and delete existing ones.",
    SCOPE_BACKUP_RESTORE: "Restore a backup into a workspace.",
    SCOPE_CONTENTS_READ: "Read the full contents of a workspace or application.",
    SCOPE_SCHEDULE_READ: "List backup schedules.",
    SCOPE_SCHEDULE_WRITE: "Create, update, delete and manually trigger schedules.",
}
