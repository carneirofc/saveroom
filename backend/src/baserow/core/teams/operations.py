from baserow.core.operations import WorkspaceCoreOperationType


class ListTeamsWorkspaceOperationType(WorkspaceCoreOperationType):
    type = "workspace.list_teams"


class CreateTeamWorkspaceOperationType(WorkspaceCoreOperationType):
    type = "workspace.create_team"


class UpdateTeamWorkspaceOperationType(WorkspaceCoreOperationType):
    type = "workspace.update_team"


class DeleteTeamWorkspaceOperationType(WorkspaceCoreOperationType):
    type = "workspace.delete_team"


class ManageTeamMembersWorkspaceOperationType(WorkspaceCoreOperationType):
    type = "workspace.manage_team_members"


TEAM_OPERATION_TYPES = [
    ListTeamsWorkspaceOperationType,
    CreateTeamWorkspaceOperationType,
    UpdateTeamWorkspaceOperationType,
    DeleteTeamWorkspaceOperationType,
    ManageTeamMembersWorkspaceOperationType,
]
