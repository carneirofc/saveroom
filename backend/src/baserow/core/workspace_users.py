"""
Adding users that already have an account to a workspace, optionally straight into
teams and with extra options registered by other apps.

With SSO the IdP only decides who may sign in; workspace admins then pick the members of
their workspace from the accounts that exist.
"""

from typing import Any, Dict, Iterable, List, Optional

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AbstractUser
from django.db.models import Q, QuerySet

from baserow.core.handler import CoreHandler
from baserow.core.models import (
    WORKSPACE_USER_PERMISSION_MEMBER,
    Workspace,
    WorkspaceUser,
)
from baserow.core.operations import AddWorkspaceUsersWorkspaceOperationType
from baserow.core.registries import workspace_users_add_option_registry
from baserow.core.teams.exceptions import TeamDoesNotExist
from baserow.core.teams.handler import TeamHandler
from baserow.core.teams.models import Team
from baserow.core.teams.operations import ManageTeamMembersWorkspaceOperationType

User = get_user_model()

CANDIDATE_SEARCH_MIN_LENGTH = 3
CANDIDATE_SEARCH_LIMIT = 20


class UsersNotFound(Exception):
    """Raised when some users to add don't exist, are deactivated or being deleted."""

    def __init__(self, user_ids: List[int]):
        self.user_ids = user_ids
        super().__init__(f"Users {user_ids} can't be added.")


def _addable_users() -> QuerySet:
    return User.objects.filter(is_active=True, profile__to_be_deleted=False)


class WorkspaceUsersService:
    def _check(self, actor: AbstractUser, workspace: Workspace):
        CoreHandler().check_permissions(
            actor,
            AddWorkspaceUsersWorkspaceOperationType.type,
            workspace=workspace,
            context=workspace,
        )

    def search_candidates(
        self, actor: AbstractUser, workspace: Workspace, search: str
    ) -> QuerySet:
        """
        Returns the accounts matching `search` by name or email that could be added to
        the workspace. A minimum search length keeps admins from listing every account
        of the instance.
        """

        self._check(actor, workspace)
        search = search.strip()
        if len(search) < CANDIDATE_SEARCH_MIN_LENGTH:
            return User.objects.none()

        return (
            _addable_users()
            .exclude(workspaceuser__workspace=workspace)
            .filter(Q(first_name__icontains=search) | Q(email__icontains=search))
            .order_by("first_name", "id")[:CANDIDATE_SEARCH_LIMIT]
        )

    def add_users(
        self,
        actor: AbstractUser,
        workspace: Workspace,
        user_ids: Iterable[int],
        permissions: str = WORKSPACE_USER_PERMISSION_MEMBER,
        team_ids: Iterable[int] = (),
        options: Optional[Dict[str, Any]] = None,
    ) -> List[WorkspaceUser]:
        """
        Adds the users to the workspace, then to the given teams, then applies the
        registered add options whose value isn't `None`. Users that are already
        members keep their current permissions, but still join the teams and get
        the options. Run it inside a transaction so a failure adds nothing.

        :raises UsersNotFound: When any of the users can't be added.
        :raises TeamDoesNotExist: When a team doesn't belong to the workspace.
        """

        self._check(actor, workspace)
        user_ids = set(user_ids)
        users = list(_addable_users().filter(id__in=user_ids).order_by("id"))
        missing = user_ids - {user.id for user in users}
        if missing:
            raise UsersNotFound(sorted(missing))
        teams = self._get_teams(actor, workspace, team_ids)

        handler = CoreHandler()
        workspace_users = [
            handler.add_user_to_workspace(workspace, user, permissions=permissions)
            for user in users
        ]

        team_handler = TeamHandler()
        for team in teams:
            team_handler.add_members(team, [user.id for user in users])

        options = options or {}
        for option_type in workspace_users_add_option_registry.get_all():
            if options.get(option_type.type) is not None:
                option_type.apply(actor, workspace, users, options[option_type.type])

        return workspace_users

    def _get_teams(
        self, actor: AbstractUser, workspace: Workspace, team_ids: Iterable[int]
    ) -> List[Team]:
        team_ids = set(team_ids)
        if not team_ids:
            return []

        CoreHandler().check_permissions(
            actor,
            ManageTeamMembersWorkspaceOperationType.type,
            workspace=workspace,
            context=workspace,
        )
        teams = list(
            Team.objects.filter(workspace=workspace, id__in=team_ids).order_by("id")
        )
        missing = team_ids - {team.id for team in teams}
        if missing:
            raise TeamDoesNotExist(
                f"The teams {sorted(missing)} do not exist in the workspace."
            )
        return teams
