from baserow.core.operations import WorkspaceCoreOperationType


class ManageDatabaseAccessWorkspaceOperationType(WorkspaceCoreOperationType):
    type = "workspace.manage_database_access"
