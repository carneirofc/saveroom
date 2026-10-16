from typing import Iterable, List

from django.contrib.auth.models import AbstractUser

from baserow.core.handler import CoreHandler
from baserow.core.models import Workspace

from .handler import TeamHandler
from .models import Team, TeamMember
from .operations import (
    CreateTeamWorkspaceOperationType,
    DeleteTeamWorkspaceOperationType,
    ListTeamsWorkspaceOperationType,
    ManageTeamMembersWorkspaceOperationType,
    UpdateTeamWorkspaceOperationType,
)


class TeamService:
    """Permission-aware orchestration of team management."""

    def __init__(self):
        self.handler = TeamHandler()

    def _check(self, user: AbstractUser, operation: str, workspace: Workspace):
        CoreHandler().check_permissions(
            user, operation, workspace=workspace, context=workspace
        )

    def get_team(self, user: AbstractUser, team_id: int) -> Team:
        team = self.handler.get_team(team_id)
        self._check(user, ListTeamsWorkspaceOperationType.type, team.workspace)
        return team

    def list_teams(self, user: AbstractUser, workspace: Workspace):
        self._check(user, ListTeamsWorkspaceOperationType.type, workspace)
        return self.handler.list_teams(workspace)

    def create_team(
        self,
        user: AbstractUser,
        workspace: Workspace,
        name: str,
        user_ids: Iterable[int] = (),
    ) -> Team:
        self._check(user, CreateTeamWorkspaceOperationType.type, workspace)
        return self.handler.create_team(workspace, name, user_ids)

    def update_team(self, user: AbstractUser, team: Team, name: str) -> Team:
        self._check(user, UpdateTeamWorkspaceOperationType.type, team.workspace)
        return self.handler.update_team(team, name)

    def delete_team(self, user: AbstractUser, team: Team) -> None:
        self._check(user, DeleteTeamWorkspaceOperationType.type, team.workspace)
        self.handler.delete_team(team)

    def add_members(
        self, user: AbstractUser, team: Team, user_ids: Iterable[int]
    ) -> List[TeamMember]:
        self._check(user, ManageTeamMembersWorkspaceOperationType.type, team.workspace)
        return self.handler.add_members(team, user_ids)

    def remove_members(
        self, user: AbstractUser, team: Team, user_ids: Iterable[int]
    ) -> int:
        self._check(user, ManageTeamMembersWorkspaceOperationType.type, team.workspace)
        return self.handler.remove_members(team, user_ids)
