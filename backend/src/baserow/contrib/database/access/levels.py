"""
Maps in-app access levels to the operations they allow.

`viewer` and `editor` are explicit allow-lists. `builder` is every operation of the
database family, so an operation added later is builder-only until it is deliberately
listed here: lower levels fail closed.
"""

from functools import lru_cache
from typing import Dict, FrozenSet

from baserow.core.operations import (
    DeleteApplicationOperationType,
    DuplicateApplicationOperationType,
    ReadApplicationOperationType,
    RestoreApplicationOperationType,
    UpdateApplicationOperationType,
)

from .models import (
    ACCESS_LEVEL_BUILDER,
    ACCESS_LEVEL_EDITOR,
    ACCESS_LEVEL_NONE,
    ACCESS_LEVEL_VIEWER,
)

DATABASE_SCOPE_TYPE = "database"

# Application operations only belong to the database family when their context is a
# database; the resolver checks that per context.
APPLICATION_OPERATIONS = frozenset(
    {
        ReadApplicationOperationType.type,
        UpdateApplicationOperationType.type,
        DuplicateApplicationOperationType.type,
        DeleteApplicationOperationType.type,
        RestoreApplicationOperationType.type,
    }
)

VIEWER_OPERATIONS = frozenset(
    {
        ReadApplicationOperationType.type,
        "database.list_tables",
        "database.table.read",
        "database.table.listen_to_all",
        "database.table.list_rows",
        "database.table.list_row_names",
        "database.table.read_row",
        "database.table.read_adjacent_row",
        "database.table.read_row_history",
        "database.table.run_export",
        "database.table.list_fields",
        "database.table.field.read",
        "database.table.field_rules.read_field_rules",
        "database.table.list_views",
        "database.table.read_view_order",
        "database.table.view.read",
        "database.table.view.read_field_options",
        "database.table.view.read_default_values",
        "database.table.view.list_fields",
        "database.table.view.list_rows",
        "database.table.view.read_row",
        "database.table.view.read_adjacent_row",
        "database.table.view.list_comments",
        "database.table.view.list_sort",
        "database.table.view.sort.read",
        "database.table.view.list_group_bys",
        "database.table.view.group_by.read",
        "database.table.view.list_filter",
        "database.table.view.filter.read",
        "database.table.view.filter_group.read",
        "database.table.view.list_decoration",
        "database.table.view.decoration.read",
        "database.table.view.list_aggregations",
        "database.table.view.read_aggregation",
        "database.data_sync.get",
        "database.data_sync.list_properties",
    }
)

# `database.table.replace_rows` is deliberately absent: an editor may import rows
# but not run the import modes that trash the existing ones, so it stays builder-only.
EDITOR_OPERATIONS = VIEWER_OPERATIONS | frozenset(
    {
        "database.table.create_row",
        "database.table.import_rows",
        "database.table.update_row",
        "database.table.move_row",
        "database.table.delete_row",
        "database.table.restore_row",
        "database.table.field.write_values",
        "database.table.create_and_use_personal_view",
        "database.table.view.create_row",
        "database.table.view.update_row",
        "database.table.view.move_row",
        "database.table.view.delete_row",
        "database.table.view.restore_row",
        "database.table.view.create_comment",
        "database.table.view.update_comment",
        "database.table.view.delete_comment",
        "database.table.view.restore_comment",
    }
)


@lru_cache(maxsize=1)
def get_database_family_operations() -> FrozenSet[str]:
    """
    Every registered operation whose context lives inside a database (the database
    itself, its tables, fields, views, ...), plus the application operations.
    """

    from baserow.core.registries import (
        object_scope_type_registry,
        operation_type_registry,
    )

    database_scope = object_scope_type_registry.get(DATABASE_SCOPE_TYPE)
    family = set(APPLICATION_OPERATIONS)
    for operation_type in operation_type_registry.get_all():
        if object_scope_type_registry.scope_type_includes_scope_type(
            database_scope, operation_type.context_scope
        ):
            family.add(operation_type.type)
    return frozenset(family)


@lru_cache(maxsize=1)
def get_level_operations() -> Dict[str, FrozenSet[str]]:
    family = get_database_family_operations()
    return {
        ACCESS_LEVEL_NONE: frozenset(),
        ACCESS_LEVEL_VIEWER: VIEWER_OPERATIONS & family,
        ACCESS_LEVEL_EDITOR: EDITOR_OPERATIONS & family,
        ACCESS_LEVEL_BUILDER: family,
    }


def level_allows(level: str, operation_name: str) -> bool:
    return operation_name in get_level_operations()[level]
