from abc import ABC

from baserow.core.operations import WorkspaceCoreOperationType
from baserow.core.registries import OperationType

from .object_scopes import TableExportScheduleObjectScopeType


class ListTableExportSchedulesOperationType(WorkspaceCoreOperationType):
    type = "workspace.list_table_export_schedules"


class CreateTableExportScheduleOperationType(WorkspaceCoreOperationType):
    type = "workspace.create_table_export_schedule"


class TableExportScheduleOperationType(OperationType, ABC):
    context_scope_name = TableExportScheduleObjectScopeType.type


class ReadTableExportScheduleOperationType(TableExportScheduleOperationType):
    type = "workspace.table_export_schedule.read"


class UpdateTableExportScheduleOperationType(TableExportScheduleOperationType):
    type = "workspace.table_export_schedule.update"


class DeleteTableExportScheduleOperationType(TableExportScheduleOperationType):
    type = "workspace.table_export_schedule.delete"
