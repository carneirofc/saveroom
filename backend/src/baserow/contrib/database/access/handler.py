from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from django.db import transaction

from baserow.contrib.database.models import Database, Table
from baserow.core.models import Workspace, WorkspaceUser
from baserow.core.signals import permissions_updated
from baserow.core.teams.models import Team, TeamMember

from .exceptions import InvalidAccessScope, InvalidAccessSubject
from .models import ACCESS_LEVELS, DatabaseAccessGrant
from .resolver import invalidate_workspace_grants_cache

SCOPE_WORKSPACE = "workspace"
SCOPE_DATABASE = "database"
SCOPE_TABLE = "table"
SCOPE_TYPES = [SCOPE_WORKSPACE, SCOPE_DATABASE, SCOPE_TABLE]
SUBJECT_TYPES = ["user", "team"]


@dataclass
class AccessScope:
    type: str
    workspace: Workspace
    database: Optional[Database] = None
    table: Optional[Table] = None

    @property
    def filter(self) -> Dict:
        return {
            "workspace": self.workspace,
            "database": self.database,
            "table": self.table,
        }

    @property
    def parents(self) -> List["AccessScope"]:
        """Scopes a grant is inherited from, nearest first."""

        if self.type == SCOPE_TABLE:
            return [
                AccessScope(
                    SCOPE_DATABASE, self.workspace, database=self.table.database
                ),
                AccessScope(SCOPE_WORKSPACE, self.workspace),
            ]
        if self.type == SCOPE_DATABASE:
            return [AccessScope(SCOPE_WORKSPACE, self.workspace)]
        return []


class DatabaseAccessHandler:
    def get_scope(self, scope_type: str, scope_id: int) -> AccessScope:
        try:
            if scope_type == SCOPE_WORKSPACE:
                return AccessScope(scope_type, Workspace.objects.get(id=scope_id))
            if scope_type == SCOPE_DATABASE:
                database = Database.objects.select_related("workspace").get(
                    id=scope_id, workspace__isnull=False
                )
                return AccessScope(scope_type, database.workspace, database=database)
            if scope_type == SCOPE_TABLE:
                table = Table.objects.select_related("database__workspace").get(
                    id=scope_id, database__workspace__isnull=False
                )
                return AccessScope(scope_type, table.database.workspace, table=table)
        except Workspace.DoesNotExist, Database.DoesNotExist, Table.DoesNotExist:
            pass
        raise InvalidAccessScope(f"{scope_type} {scope_id}")

    def list_subjects(self, workspace: Workspace):
        members = list(
            WorkspaceUser.objects.filter(workspace=workspace)
            .select_related("user")
            .order_by("user__first_name", "user__id")
        )
        teams = list(Team.objects.filter(workspace=workspace))
        return members, teams

    def get_scope_grants(self, scope: AccessScope) -> Dict[Tuple[str, int], str]:
        return {
            (grant.subject_type, grant.user_id or grant.team_id): grant.level
            for grant in DatabaseAccessGrant.objects.filter(**scope.filter)
        }

    def get_inherited_grants(
        self, scope: AccessScope
    ) -> Dict[Tuple[str, int], Tuple[str, str]]:
        """Per subject, the nearest parent-scope grant as `(level, scope_type)`."""

        inherited = {}
        for parent in scope.parents:
            for key, level in self.get_scope_grants(parent).items():
                inherited.setdefault(key, (level, parent.type))
        return inherited

    def set_grants(self, scope: AccessScope, grants: List[Dict]) -> None:
        """
        Sets the grants of the given subjects on the scope. A `level` of `None` removes
        the subject's grant, so it inherits again.
        """

        workspace = scope.workspace
        user_ids = {g["subject_id"] for g in grants if g["subject_type"] == "user"}
        team_ids = {g["subject_id"] for g in grants if g["subject_type"] == "team"}

        valid_user_ids = set(
            WorkspaceUser.objects.filter(
                workspace=workspace, user_id__in=user_ids
            ).values_list("user_id", flat=True)
        )
        valid_team_ids = set(
            Team.objects.filter(workspace=workspace, id__in=team_ids).values_list(
                "id", flat=True
            )
        )
        if user_ids - valid_user_ids or team_ids - valid_team_ids:
            raise InvalidAccessSubject(
                sorted(user_ids - valid_user_ids), sorted(team_ids - valid_team_ids)
            )

        for grant in grants:
            if grant["level"] is not None and grant["level"] not in ACCESS_LEVELS:
                raise ValueError(f"Unknown access level {grant['level']}")

        with transaction.atomic():
            for grant in grants:
                subject = {
                    "user_id": None,
                    "team_id": None,
                    f"{grant['subject_type']}_id": grant["subject_id"],
                }
                queryset = DatabaseAccessGrant.objects.filter(**scope.filter, **subject)
                if grant["level"] is None:
                    queryset.delete()
                elif not queryset.update(level=grant["level"]):
                    DatabaseAccessGrant.objects.create(
                        **scope.filter, **subject, level=grant["level"]
                    )

        invalidate_workspace_grants_cache(workspace.id)
        transaction.on_commit(lambda: invalidate_workspace_grants_cache(workspace.id))

        affected = set(valid_user_ids) | set(
            TeamMember.objects.filter(team_id__in=valid_team_ids).values_list(
                "user_id", flat=True
            )
        )
        if affected:
            permissions_updated.send(self, workspace=workspace, user_ids=affected)
