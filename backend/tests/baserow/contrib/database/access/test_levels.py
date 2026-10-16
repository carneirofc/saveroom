import pytest

from baserow.contrib.database.access.levels import (
    EDITOR_OPERATIONS,
    VIEWER_OPERATIONS,
    get_database_family_operations,
    get_level_operations,
    level_allows,
)
from baserow.core.registries import operation_type_registry


@pytest.mark.django_db
def test_levels_are_strictly_nested():
    levels = get_level_operations()

    assert levels["none"] == frozenset()
    assert levels["viewer"] < levels["editor"] < levels["builder"]
    assert levels["builder"] == get_database_family_operations()


@pytest.mark.django_db
def test_every_listed_operation_is_registered():
    registered = {operation.type for operation in operation_type_registry.get_all()}

    assert VIEWER_OPERATIONS <= registered
    assert EDITOR_OPERATIONS <= registered


@pytest.mark.django_db
def test_family_covers_database_subtree_and_excludes_other_components():
    family = get_database_family_operations()

    for operation in [
        "database.create_table",
        "database.list_tables",
        "database.table.create_field",
        "database.table.field.update",
        "database.table.view.filter.update",
        "database.table.view.decoration.delete",
        "application.read",
    ]:
        assert operation in family

    for operation in [
        "workspace.read",
        "workspace.create_application",
        "workspace.list_applications",
        "workspace.manage_database_access",
        "builder.page.create",
    ]:
        assert operation not in family


@pytest.mark.django_db
@pytest.mark.parametrize(
    "level,operation,allowed",
    [
        ("viewer", "database.table.list_rows", True),
        ("viewer", "database.table.create_row", False),
        ("editor", "database.table.create_row", True),
        ("editor", "database.table.update_row", True),
        ("editor", "database.table.create_field", False),
        ("editor", "database.table.import_rows", True),
        ("editor", "database.table.replace_rows", False),
        ("builder", "database.table.replace_rows", True),
        ("editor", "database.table.view.update", False),
        ("builder", "database.table.create_field", True),
        ("builder", "database.table.delete", True),
        ("none", "database.table.read", False),
    ],
)
def test_level_allows(level, operation, allowed):
    assert level_allows(level, operation) is allowed
