from django.contrib.auth import get_user_model

from baserow.contrib.database.fields.operations import (
    ListFieldsOperationType,
    SubmitAnonymousFieldValuesOperationType,
    WriteFieldValuesOperationType,
)
from baserow.contrib.database.operations import ListTablesDatabaseTableOperationType
from baserow.contrib.database.rows.operations import ReadDatabaseRowOperationType
from baserow.contrib.database.table.operations import ListRowsDatabaseTableOperationType
from baserow.contrib.database.views.operations import (
    ListAggregationsViewOperationType,
    ListViewDecorationOperationType,
    ListViewsOperationType,
    ReadAggregationsViewOperationType,
    ReadViewFieldOptionsOperationType,
    ReadViewOperationType,
)
from baserow.core.permission_manager import (
    AllowIfTemplatePermissionManagerType as CoreAllowIfTemplatePermissionManagerType,
)
from baserow.core.registries import PermissionManagerType
from baserow.core.subjects import AnonymousUserSubjectType, UserSubjectType

User = get_user_model()


class AllowIfTemplatePermissionManagerType(CoreAllowIfTemplatePermissionManagerType):
    """
    Allows read operation on templates.
    """

    DATABASE_OPERATION_ALLOWED_ON_TEMPLATES = [
        ListTablesDatabaseTableOperationType.type,
        ListFieldsOperationType.type,
        ListRowsDatabaseTableOperationType.type,
        ListViewsOperationType.type,
        ReadDatabaseRowOperationType.type,
        ReadViewOperationType.type,
        ReadViewFieldOptionsOperationType.type,
        ListViewDecorationOperationType.type,
        ListAggregationsViewOperationType.type,
        ReadAggregationsViewOperationType.type,
    ]

    @property
    def OPERATION_ALLOWED_ON_TEMPLATES(self):
        return (
            self.prev_manager_type.OPERATION_ALLOWED_ON_TEMPLATES
            + self.DATABASE_OPERATION_ALLOWED_ON_TEMPLATES
        )

    def __init__(self, prev_manager_type: PermissionManagerType):
        self.prev_manager_type = prev_manager_type


class FieldValuePermissionManagerType(PermissionManagerType):
    """
    Field level write permissions are a plugin feature. Without a plugin restricting
    them, writing a value is only gated by the workspace level managers that already
    ran before this one, so the remaining checks are always allowed.
    """

    type = "write_field_values"
    supported_actor_types = [
        UserSubjectType.type,
        AnonymousUserSubjectType.type,
    ]

    ALWAYS_ALLOWED_OPERATIONS = [
        WriteFieldValuesOperationType.type,
        SubmitAnonymousFieldValuesOperationType.type,
    ]

    def check_multiple_permissions(self, checks, workspace=None, include_trash=False):
        return {
            check: True
            for check in checks
            if check.operation_name in self.ALWAYS_ALLOWED_OPERATIONS
        }
