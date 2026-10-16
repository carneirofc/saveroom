"""
Resolution of the effective in-app access level of workspace members.

For a member and a table the most specific scope with an applicable grant decides:
table, then database, then the workspace default. Within one scope a grant given to
the user directly beats the grants of its teams; between teams the highest level wins.
ADMINs are never restricted and a member without any applicable grant resolves to
`None`, which leaves the decision to the other permission managers.
"""

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, Iterable, Optional, Set, Tuple

from django.core.cache import cache
from django.db.models import Q

from baserow.core.models import (
    WORKSPACE_USER_PERMISSION_ADMIN,
    Application,
    Workspace,
    WorkspaceUser,
)
from baserow.core.teams.models import TeamMember

from .models import ACCESS_LEVEL_NONE, ACCESS_LEVELS, DatabaseAccessGrant

GRANTS_EXIST_CACHE_KEY = "database_access_grants_exist_{workspace_id}"


def _highest(levels: Iterable[str]) -> str:
    return max(levels, key=ACCESS_LEVELS.index)


@dataclass
class EffectiveAccess:
    """The flattened grants applying to one member of one workspace."""

    workspace: Optional[str] = None
    databases: Dict[int, str] = field(default_factory=dict)
    tables: Dict[int, str] = field(default_factory=dict)
    # Databases containing at least one table the member can access; such a database
    # stays visible even when its own level is `none`.
    databases_with_accessible_tables: Set[int] = field(default_factory=set)

    @property
    def is_empty(self) -> bool:
        return self.workspace is None and not self.databases and not self.tables

    def level_for(
        self, table_id: Optional[int], database_id: Optional[int]
    ) -> Optional[str]:
        if table_id is not None and table_id in self.tables:
            return self.tables[table_id]
        if database_id is not None and database_id in self.databases:
            return self.databases[database_id]
        return self.workspace


def workspace_has_grants(workspace_id: int) -> bool:
    key = GRANTS_EXIST_CACHE_KEY.format(workspace_id=workspace_id)
    exists = cache.get(key)
    if exists is None:
        exists = DatabaseAccessGrant.objects.filter(workspace_id=workspace_id).exists()
        cache.set(key, exists, timeout=None)
    return exists


def invalidate_workspace_grants_cache(workspace_id: int) -> None:
    cache.delete(GRANTS_EXIST_CACHE_KEY.format(workspace_id=workspace_id))


def _collapse(
    direct: Dict[object, str], via_teams: Dict[object, Set[str]]
) -> Dict[object, str]:
    result = {key: _highest(levels) for key, levels in via_teams.items()}
    result.update(direct)
    return result


def load_effective_access(
    workspace: Workspace, user_ids: Iterable[int], include_trash: bool = False
) -> Dict[int, EffectiveAccess]:
    """
    Loads the effective access of the given users in constant queries. Users that are
    ADMINs, not members, or without any applicable grant are absent from the result.
    """

    user_ids = set(user_ids)
    if not user_ids or not workspace_has_grants(workspace.id):
        return {}

    workspace_users = (
        WorkspaceUser.objects_and_trash if include_trash else WorkspaceUser.objects
    )
    member_ids = set(
        workspace_users.filter(workspace=workspace, user_id__in=user_ids)
        .exclude(permissions=WORKSPACE_USER_PERMISSION_ADMIN)
        .values_list("user_id", flat=True)
    )
    if not member_ids:
        return {}

    teams_by_user = defaultdict(set)
    for user_id, team_id in TeamMember.objects.filter(
        team__workspace=workspace, user_id__in=member_ids
    ).values_list("user_id", "team_id"):
        teams_by_user[user_id].add(team_id)
    users_by_team = defaultdict(set)
    for user_id, team_ids in teams_by_user.items():
        for team_id in team_ids:
            users_by_team[team_id].add(user_id)

    # (scope_key) -> level, per user, split in direct and via teams.
    direct = defaultdict(dict)
    via_teams = defaultdict(lambda: defaultdict(set))
    for user_id, team_id, database_id, table_id, level in (
        DatabaseAccessGrant.objects.filter(workspace=workspace)
        .filter(Q(user_id__in=member_ids) | Q(team_id__in=list(users_by_team)))
        .values_list("user_id", "team_id", "database_id", "table_id", "level")
    ):
        if table_id is not None:
            scope_key = ("table", table_id)
        elif database_id is not None:
            scope_key = ("database", database_id)
        else:
            scope_key = ("workspace", None)

        if user_id is not None:
            direct[user_id][scope_key] = level
        else:
            for member_id in users_by_team[team_id]:
                via_teams[member_id][scope_key].add(level)

    result = {}
    accessible_table_ids = set()
    for user_id in member_ids:
        scopes = _collapse(direct.get(user_id, {}), via_teams.get(user_id, {}))
        if not scopes:
            continue
        access = EffectiveAccess()
        for (scope_type, scope_id), level in scopes.items():
            if scope_type == "table":
                access.tables[scope_id] = level
                if level != ACCESS_LEVEL_NONE:
                    accessible_table_ids.add(scope_id)
            elif scope_type == "database":
                access.databases[scope_id] = level
            else:
                access.workspace = level
        result[user_id] = access

    if accessible_table_ids:
        from baserow.contrib.database.table.models import Table

        database_by_table = dict(
            Table.objects_and_trash.filter(id__in=accessible_table_ids).values_list(
                "id", "database_id"
            )
        )
        for access in result.values():
            access.databases_with_accessible_tables = {
                database_by_table[table_id]
                for table_id, level in access.tables.items()
                if level != ACCESS_LEVEL_NONE and table_id in database_by_table
            }

    return result


def resolve_contexts(
    contexts: Iterable[object],
) -> Dict[int, Tuple[Optional[int], Optional[int]]]:
    """
    Maps each context object (by `id()`) to the `(table_id, database_id)` it lives in.
    Contexts outside of any database map to `(None, None)`.
    """

    from baserow.contrib.database.models import Database
    from baserow.contrib.database.table.models import Table

    resolved = {}
    table_ids_without_database = set()
    application_ids = set()

    def walk(context):
        current = context
        for _ in range(8):
            if current is None:
                return None, None
            if isinstance(current, Table):
                return current.id, current.database_id
            if isinstance(current, Database):
                return None, current.id
            if isinstance(current, Application):
                return None, ("application", current.id)
            table_id = getattr(current, "table_id", None)
            if table_id is not None:
                return table_id, None
            get_parent = getattr(current, "get_parent", None)
            if get_parent is None:
                return None, None
            current = get_parent()
        return None, None

    for context in contexts:
        table_id, database_id = walk(context)
        if isinstance(database_id, tuple):
            application_ids.add(database_id[1])
        elif table_id is not None and database_id is None:
            table_ids_without_database.add(table_id)
        resolved[id(context)] = (table_id, database_id)

    database_by_table = {}
    if table_ids_without_database:
        database_by_table = dict(
            Table.objects_and_trash.filter(
                id__in=table_ids_without_database
            ).values_list("id", "database_id")
        )
    database_application_ids = set()
    if application_ids:
        database_application_ids = set(
            Database.objects_and_trash.filter(id__in=application_ids).values_list(
                "id", flat=True
            )
        )

    for key, (table_id, database_id) in resolved.items():
        if isinstance(database_id, tuple):
            app_id = database_id[1]
            resolved[key] = (
                (None, app_id) if app_id in database_application_ids else (None, None)
            )
        elif table_id is not None and database_id is None:
            resolved[key] = (table_id, database_by_table.get(table_id))

    return resolved
