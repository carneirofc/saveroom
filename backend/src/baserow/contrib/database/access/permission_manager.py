from django.db.models import Q

from baserow.core.operations import (
    ListApplicationsWorkspaceOperationType,
    ReadApplicationOperationType,
)
from baserow.core.registries import PermissionManagerType
from baserow.core.subjects import UserSubjectType

from .exceptions import DatabaseAccessDeniedError
from .levels import (
    get_database_family_operations,
    get_level_operations,
    level_allows,
)
from .models import (
    ACCESS_LEVEL_BUILDER,
    ACCESS_LEVEL_EDITOR,
    ACCESS_LEVEL_NONE,
    ACCESS_LEVEL_VIEWER,
)
from .resolver import load_effective_access, resolve_contexts

LIST_TABLES_OPERATION = "database.list_tables"

# Operations on a database that stay available when the database itself resolves to
# `none` but the member can still access one of its tables, so that table is reachable.
DATABASE_PASSTHROUGH_OPERATIONS = {
    ReadApplicationOperationType.type,
    LIST_TABLES_OPERATION,
}


def effective_level(access, table_id, database_id):
    level = access.level_for(table_id, database_id)
    if (
        level == ACCESS_LEVEL_NONE
        and table_id is None
        and database_id in access.databases_with_accessible_tables
    ):
        return ACCESS_LEVEL_VIEWER, True
    return level, False


class DatabaseAccessPermissionManagerType(PermissionManagerType):
    """
    Applies the in-app access levels (`DatabaseAccessGrant`) given to workspace members
    and teams on databases and tables. Only decides database-family operations for
    non-admin members with an applicable grant; everything else passes through.
    """

    type = "database_access"
    supported_actor_types = [UserSubjectType.type]

    def check_multiple_permissions(self, checks, workspace=None, include_trash=False):
        if workspace is None:
            return {}

        family = get_database_family_operations()
        family_checks = [c for c in checks if c.operation_name in family]
        if not family_checks:
            return {}

        access_by_user = load_effective_access(
            workspace, {c.actor.id for c in family_checks}, include_trash=include_trash
        )
        if not access_by_user:
            return {}

        relevant = [c for c in family_checks if c.actor.id in access_by_user]
        locations = resolve_contexts(c.context for c in relevant)

        result = {}
        for check in relevant:
            table_id, database_id = locations[id(check.context)]
            if table_id is None and database_id is None:
                continue

            level, database_passthrough = effective_level(
                access_by_user[check.actor.id], table_id, database_id
            )
            if level is None:
                continue

            if database_passthrough:
                allowed = check.operation_name in DATABASE_PASSTHROUGH_OPERATIONS
            else:
                allowed = level_allows(level, check.operation_name)

            result[check] = (
                True
                if allowed
                else DatabaseAccessDeniedError(
                    check.actor, workspace, level, check.operation_name
                )
            )
        return result

    def filter_queryset(self, actor, operation_name, queryset, workspace=None):
        if workspace is None or operation_name not in (
            LIST_TABLES_OPERATION,
            ListApplicationsWorkspaceOperationType.type,
        ):
            return None

        access = load_effective_access(workspace, [actor.id]).get(actor.id)
        if access is None:
            return None

        allowed_tables = {t for t, lvl in access.tables.items() if lvl != "none"}
        denied_tables = {t for t, lvl in access.tables.items() if lvl == "none"}
        allowed_databases = {
            d for d, lvl in access.databases.items() if lvl != "none"
        } | access.databases_with_accessible_tables
        denied_databases = {
            d for d, lvl in access.databases.items() if lvl == "none"
        } - access.databases_with_accessible_tables
        workspace_denied = access.workspace == ACCESS_LEVEL_NONE

        if operation_name == LIST_TABLES_OPERATION:
            exclude = Q(id__in=denied_tables) | (
                Q(database_id__in=denied_databases) & ~Q(id__in=allowed_tables)
            )
            if workspace_denied:
                exclude |= ~Q(id__in=allowed_tables) & ~Q(
                    database_id__in={
                        d for d, lvl in access.databases.items() if lvl != "none"
                    }
                )
            return queryset.exclude(exclude)

        from baserow.contrib.database.models import Database

        exclude = Q(id__in=denied_databases)
        if workspace_denied:
            exclude |= Q(
                id__in=Database.objects.filter(workspace=workspace).values("id")
            ) & ~Q(id__in=allowed_databases)
        return queryset.exclude(exclude)

    def get_permissions_object(self, actor, workspace=None):
        if workspace is None:
            return None

        access = load_effective_access(workspace, [actor.id]).get(actor.id)
        if access is None:
            return None

        levels = get_level_operations()
        return {
            "workspace": access.workspace,
            "databases": access.databases,
            "tables": access.tables,
            "databases_with_accessible_tables": sorted(
                access.databases_with_accessible_tables
            ),
            "family_operations": sorted(get_database_family_operations()),
            "level_operations": {
                ACCESS_LEVEL_VIEWER: sorted(levels[ACCESS_LEVEL_VIEWER]),
                ACCESS_LEVEL_EDITOR: sorted(levels[ACCESS_LEVEL_EDITOR]),
                ACCESS_LEVEL_BUILDER: sorted(levels[ACCESS_LEVEL_BUILDER]),
            },
            "database_passthrough_operations": sorted(DATABASE_PASSTHROUGH_OPERATIONS),
        }
