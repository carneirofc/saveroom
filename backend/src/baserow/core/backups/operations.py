from abc import ABC

from baserow.core.backups.object_scopes import BackupScheduleObjectScopeType
from baserow.core.operations import WorkspaceCoreOperationType
from baserow.core.registries import OperationType


class ListBackupSchedulesOperationType(WorkspaceCoreOperationType):
    type = "workspace.list_backup_schedules"


class CreateBackupScheduleOperationType(WorkspaceCoreOperationType):
    type = "workspace.create_backup_schedule"


class BackupScheduleOperationType(OperationType, ABC):
    context_scope_name = BackupScheduleObjectScopeType.type


class ReadBackupScheduleOperationType(BackupScheduleOperationType):
    type = "workspace.backup_schedule.read"


class UpdateBackupScheduleOperationType(BackupScheduleOperationType):
    type = "workspace.backup_schedule.update"


class DeleteBackupScheduleOperationType(BackupScheduleOperationType):
    type = "workspace.backup_schedule.delete"
