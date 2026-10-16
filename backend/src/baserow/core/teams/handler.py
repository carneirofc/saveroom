from typing import Iterable, List, Optional

from django.contrib.auth.models import AbstractUser
from django.db import IntegrityError, transaction
from django.db.models import QuerySet

from baserow.core.models import Workspace, WorkspaceUser
from baserow.core.signals import permissions_updated

from .exceptions import TeamDoesNotExist, TeamMemberNotInWorkspace, TeamNameNotUnique
from .models import TEAM_MEMBER_SOURCE_MANUAL, Team, TeamMember


class TeamHandler:
    """Persistence of teams and their members. Permission checks live in the service."""

    def get_team(self, team_id: int, base_queryset: Optional[QuerySet] = None) -> Team:
        queryset = base_queryset if base_queryset is not None else Team.objects
        try:
            return queryset.select_related("workspace").get(id=team_id)
        except Team.DoesNotExist:
            raise TeamDoesNotExist(f"The team {team_id} does not exist.")

    def list_teams(self, workspace: Workspace) -> QuerySet[Team]:
        return Team.objects.filter(workspace=workspace).prefetch_related(
            "members__user"
        )

    def create_team(
        self, workspace: Workspace, name: str, user_ids: Iterable[int] = ()
    ) -> Team:
        try:
            with transaction.atomic():
                team = Team.objects.create(workspace=workspace, name=name.strip())
        except IntegrityError:
            raise TeamNameNotUnique(name)

        if user_ids:
            self.add_members(team, user_ids)
        return team

    def update_team(self, team: Team, name: str) -> Team:
        team.name = name.strip()
        try:
            with transaction.atomic():
                team.save(update_fields=["name", "updated_on"])
        except IntegrityError:
            raise TeamNameNotUnique(name)
        return team

    def delete_team(self, team: Team) -> None:
        user_ids = list(team.members.values_list("user_id", flat=True))
        workspace = team.workspace
        team.delete()
        self._notify(workspace, user_ids)

    def _validate_members(self, workspace: Workspace, user_ids: Iterable[int]):
        user_ids = set(user_ids)
        in_workspace = set(
            WorkspaceUser.objects.filter(
                workspace=workspace, user_id__in=user_ids
            ).values_list("user_id", flat=True)
        )
        missing = user_ids - in_workspace
        if missing:
            raise TeamMemberNotInWorkspace(sorted(missing))
        return user_ids

    def add_members(
        self,
        team: Team,
        user_ids: Iterable[int],
        source: str = TEAM_MEMBER_SOURCE_MANUAL,
    ) -> List[TeamMember]:
        """
        Adds the users to the team. Users already in the team keep their membership
        and its source, so a manual membership is never turned into an SSO one.
        """

        user_ids = self._validate_members(team.workspace, user_ids)
        existing = set(team.members.values_list("user_id", flat=True))
        new_members = TeamMember.objects.bulk_create(
            [
                TeamMember(team=team, user_id=user_id, source=source)
                for user_id in user_ids - existing
            ]
        )
        self._notify(team.workspace, [m.user_id for m in new_members])
        return new_members

    def remove_members(
        self, team: Team, user_ids: Iterable[int], source: Optional[str] = None
    ) -> int:
        """
        Removes the users from the team. When `source` is given, only memberships
        created by that source are removed.
        """

        queryset = team.members.filter(user_id__in=list(user_ids))
        if source is not None:
            queryset = queryset.filter(source=source)
        removed_user_ids = list(queryset.values_list("user_id", flat=True))
        queryset.delete()
        self._notify(team.workspace, removed_user_ids)
        return len(removed_user_ids)

    def remove_user_from_workspace_teams(
        self, user: AbstractUser, workspace_id: int
    ) -> None:
        TeamMember.objects.filter(user=user, team__workspace_id=workspace_id).delete()

    def _notify(self, workspace: Workspace, user_ids: Iterable[int]) -> None:
        user_ids = list(set(user_ids))
        if user_ids:
            permissions_updated.send(self, workspace=workspace, user_ids=user_ids)
