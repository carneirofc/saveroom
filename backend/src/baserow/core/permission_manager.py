from typing import Iterable, List, Optional

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AbstractUser
from django.contrib.contenttypes.models import ContentType

from baserow.contrib.database.access.operations import (
    ManageDatabaseAccessWorkspaceOperationType,
)
from baserow.contrib.database.field_rules.operations import ReadFieldRuleOperationType
from baserow.contrib.database.tokens.subjects import TokenSubjectType
from baserow.core.cache import local_cache
from baserow.core.handler import CoreHandler
from baserow.core.integrations.operations import (
    ListIntegrationsApplicationOperationType,
)
from baserow.core.models import Template, Workspace, WorkspaceUser
from baserow.core.notifications.operations import (
    ClearNotificationsOperationType,
    ListNotificationsOperationType,
    MarkNotificationAsReadOperationType,
)
from baserow.core.object_scopes import ApplicationObjectScopeType
from baserow.core.user_sources.operations import (
    ListUserSourcesApplicationOperationType,
    LoginUserSourceOperationType,
)
from baserow.core.user_sources.subjects import UserSourceUserSubjectType

from .backups.operations import (
    CreateBackupScheduleOperationType,
    DeleteBackupScheduleOperationType,
    ListBackupSchedulesOperationType,
    ReadBackupScheduleOperationType,
    UpdateBackupScheduleOperationType,
)
from .exceptions import (
    IsNotAdminError,
    PermissionDenied,
    UserInvalidWorkspacePermissionsError,
    UserNotInWorkspace,
)
from .operations import (
    AddWorkspaceUsersWorkspaceOperationType,
    CreateApplicationsWorkspaceOperationType,
    CreateWorkspaceOperationType,
    DeleteWorkspaceOperationType,
    DeleteWorkspaceUserOperationType,
    ExportWorkspaceOperationType,
    ListApplicationsWorkspaceOperationType,
    ListWorkspacesOperationType,
    ListWorkspaceUsersWorkspaceOperationType,
    ReadWorkspaceOperationType,
    UpdateSettingsOperationType,
    UpdateWorkspaceOperationType,
    UpdateWorkspaceUserOperationType,
)
from .registries import (
    PermissionManagerType,
    application_type_registry,
    object_scope_type_registry,
    operation_type_registry,
)
from .subjects import AnonymousUserSubjectType, UserSubjectType
from .teams.operations import TEAM_OPERATION_TYPES

User = get_user_model()


class CorePermissionManagerType(PermissionManagerType):
    """
    Some operation are always allowed. This permission manager handle this case.
    """

    type = "core"
    supported_actor_types = [UserSubjectType.type]

    ALWAYS_ALLOWED_OPERATIONS = [
        ListWorkspacesOperationType.type,
    ]

    def check_multiple_permissions(self, checks, workspace=None, include_trash=False):
        result = {}
        for check in checks:
            if check.operation_name in self.ALWAYS_ALLOWED_OPERATIONS:
                result[check] = True
        return result

    def get_permissions_object(self, actor, workspace=None):
        return self.ALWAYS_ALLOWED_OPERATIONS


class StaffOnlyPermissionManagerType(PermissionManagerType):
    """
    Checks if a user is_staff if the required operation is for staff only.
    """

    type = "staff"
    supported_actor_types = [UserSubjectType.type]

    STAFF_ONLY_OPERATIONS = [UpdateSettingsOperationType.type]

    def check_multiple_permissions(self, checks, workspace=None, include_trash=False):
        result = {}
        for check in checks:
            if check.operation_name in self.STAFF_ONLY_OPERATIONS:
                if check.actor.is_staff:
                    result[check] = True
                else:
                    result[check] = IsNotAdminError(check.actor)

        return result

    def get_permissions_object(self, actor, workspace=None):
        return {
            "staff_only_operations": self.STAFF_ONLY_OPERATIONS,
            "is_staff": actor.is_staff,
        }


class StaffBypassPermissionManagerType(PermissionManagerType):
    """
    Grants staff an extra allowance on top of whatever the other permission
    managers decide, for a short list of operations a staff member should be able
    to perform on any workspace regardless of membership (e.g. managing backups
    from the admin area). Unlike `StaffOnlyPermissionManagerType`, this manager
    never denies: for a non-staff actor, or for an operation not in the list, it
    leaves the check undetermined so the normal `member`-based managers still
    decide it. This must run before the `member` permission manager in
    `settings.PERMISSION_MANAGERS`.
    """

    type = "staff_bypass"
    supported_actor_types = [UserSubjectType.type]

    # Reused, workspace-membership-scoped operations that a staff member must also
    # be able to perform on workspaces they are not a member of, so the admin
    # backups UI can manage backups/restores across every workspace. Regular,
    # non-staff use of these same operations by workspace members is untouched.
    STAFF_BYPASS_OPERATIONS = [
        ExportWorkspaceOperationType.type,
        CreateApplicationsWorkspaceOperationType.type,
        ListBackupSchedulesOperationType.type,
        CreateBackupScheduleOperationType.type,
        ReadBackupScheduleOperationType.type,
        UpdateBackupScheduleOperationType.type,
        DeleteBackupScheduleOperationType.type,
    ]

    def check_multiple_permissions(self, checks, workspace=None, include_trash=False):
        result = {}
        for check in checks:
            if check.operation_name in self.STAFF_BYPASS_OPERATIONS and getattr(
                check.actor, "is_staff", False
            ):
                result[check] = True
        return result

    def filter_queryset(self, actor, operation_name, queryset, workspace=None):
        """
        A staff member exporting a workspace they are not a member of must see every
        application in it. Without this the `member` manager empties the queryset
        and the backup would contain nothing. For workspaces the staff member belongs
        to, the regular managers keep deciding.
        """

        if (
            operation_name != ListApplicationsWorkspaceOperationType.type
            or workspace is None
            or not getattr(actor, "is_staff", False)
        ):
            return None

        if WorkspaceUser.objects.filter(
            user_id=actor.id, workspace_id=workspace.id
        ).exists():
            return None

        return queryset, True


class AllowIfTemplatePermissionManagerType(PermissionManagerType):
    """
    Allows read operation on templates.
    """

    type = "allow_if_template"
    supported_actor_types = [UserSubjectType.type, AnonymousUserSubjectType.type]

    OPERATION_ALLOWED_ON_TEMPLATES = [
        ReadWorkspaceOperationType.type,
        ListApplicationsWorkspaceOperationType.type,
        ListIntegrationsApplicationOperationType.type,
        ListUserSourcesApplicationOperationType.type,
        LoginUserSourceOperationType.type,
        ReadFieldRuleOperationType.type,
    ]

    def check_multiple_permissions(self, checks, workspace=None, include_trash=False):
        result = {}

        def has_template():
            return workspace and workspace.has_template()

        for check in checks:
            if (
                check.operation_name in self.OPERATION_ALLOWED_ON_TEMPLATES
                and has_template()
            ):
                result[check] = True

        return result

    def get_permissions_object(self, actor, workspace=None):
        return {
            "allowed_operations_on_templates": self.OPERATION_ALLOWED_ON_TEMPLATES,
            "workspace_template_ids": list(
                Template.objects.values_list("workspace_id", flat=True)
            ),
        }

    def filter_queryset(
        self,
        actor,
        operation_name,
        queryset,
        workspace=None,
    ):
        def has_template():
            return workspace and workspace.has_template()

        if operation_name in self.OPERATION_ALLOWED_ON_TEMPLATES and has_template():
            return queryset, True


class WorkspaceMemberOnlyPermissionManagerType(PermissionManagerType):
    """
    To be able to operate on a workspace, the user must at least belongs
    to that workspace.
    """

    type = "member"
    supported_actor_types = [UserSubjectType.type]
    actor_cache_key = "_in_workspace_cache"

    ALWAYS_ALLOWED_OPERATION_FOR_WORKSPACE_MEMBERS: List[str] = [
        ClearNotificationsOperationType.type,
        ListNotificationsOperationType.type,
        MarkNotificationAsReadOperationType.type,
    ]

    def is_actor_in_workspace(self, actor, workspace, callback=None):
        """
        Check is an actor is in a workspace. This method cache the result on the actor
        to prevent extra queries when used multiple times in a row. This is the case
        when we check the permission first then we filter the queryset for instance.

        :param actor: the actor to check.
        :param workspace: the workspace to check the actor belongs to.
        :param callback: an optional callback to check whether the actor belongs to the
          workspace. By default a query is made if not provided.
        """

        # Add cache to prevent another query during the filtering if any
        if not hasattr(actor, self.actor_cache_key):
            setattr(actor, self.actor_cache_key, {})

        if workspace.id not in getattr(actor, self.actor_cache_key):
            if callback is not None:
                in_workspace = callback()
            else:

                def _in_workspace():
                    user_iterator = (
                        wu.user_id
                        for wu in workspace.workspaceuser_set.all()
                        if wu.user_id == actor.id
                    )
                    return next(user_iterator, None) is not None

                in_workspace = local_cache.get(
                    f"user_{actor.id}_in_workspace_{workspace.id}", _in_workspace
                )

            getattr(actor, self.actor_cache_key)[workspace.id] = in_workspace

        return getattr(actor, self.actor_cache_key, {}).get(workspace.id, False)

    def get_user_ids_map_actually_in_workspace(
        self,
        workspace: Workspace,
        users_to_query: Iterable[AbstractUser],
        include_trash: bool = False,
    ):
        """
        Return a `user_id -> is in the workspace` map. This version is cached for
        a few seconds to prevent queries.
        """

        cached = local_cache.get(f"workspace_user_{workspace.id}", dict)

        missing = []
        for user in users_to_query:
            if user.id not in cached:
                missing.append(user)

        if missing:
            user_ids_in_workspace = set(
                CoreHandler()
                .get_workspace_users(workspace, missing, include_trash=include_trash)
                .values_list("user_id", flat=True)
            )

            for missing_user in missing:
                cached[missing_user.id] = missing_user.id in user_ids_in_workspace

        return cached

    def check_multiple_permissions(self, checks, workspace=None, include_trash=False):
        if workspace is None:
            return {}

        user_id_map_in_workspace = self.get_user_ids_map_actually_in_workspace(
            workspace, {c.actor for c in checks}, include_trash=include_trash
        )

        permission_by_check = {}

        def check_workspace(actor):
            return lambda: user_id_map_in_workspace[actor.id]

        for check in checks:
            if self.is_actor_in_workspace(
                check.actor, workspace, check_workspace(check.actor)
            ):
                if (
                    check.operation_name
                    in self.ALWAYS_ALLOWED_OPERATION_FOR_WORKSPACE_MEMBERS
                ):
                    permission_by_check[check] = True
            else:
                permission_by_check[check] = UserNotInWorkspace(check.actor, workspace)

        return permission_by_check

    def get_permissions_object(self, actor, workspace=None):
        """Check if the user is a member of this workspace"""

        if workspace and self.is_actor_in_workspace(actor, workspace):
            return None

        return False

    def filter_queryset(
        self,
        actor,
        operation_name,
        queryset,
        workspace=None,
    ):
        if workspace and not self.is_actor_in_workspace(actor, workspace):
            return queryset.none(), True


class BasicPermissionManagerType(PermissionManagerType):
    """
    This permission manager check if the user is an admin when the operation is admin
    only.
    """

    type = "basic"
    supported_actor_types = [UserSubjectType.type]

    ADMIN_ONLY_OPERATIONS = [
        ListWorkspaceUsersWorkspaceOperationType.type,
        UpdateWorkspaceOperationType.type,
        DeleteWorkspaceOperationType.type,
        UpdateWorkspaceUserOperationType.type,
        DeleteWorkspaceUserOperationType.type,
        AddWorkspaceUsersWorkspaceOperationType.type,
        *[team_operation_type.type for team_operation_type in TEAM_OPERATION_TYPES],
        ManageDatabaseAccessWorkspaceOperationType.type,
    ]

    def check_multiple_permissions(self, checks, workspace=None, include_trash=False):
        if workspace is None:
            return {}

        permission_by_check = {}
        users_to_query = set()
        for check in checks:
            if check.operation_name in self.ADMIN_ONLY_OPERATIONS:
                users_to_query.add(check.actor)
            else:
                permission_by_check[check] = True

        user_permissions_by_id = dict(
            CoreHandler()
            .get_workspace_users(workspace, users_to_query, include_trash=include_trash)
            .values_list("user_id", "permissions")
        )

        for check in checks:
            if check.operation_name in self.ADMIN_ONLY_OPERATIONS:
                if user_permissions_by_id.get(check.actor.id, "MEMBER") == "ADMIN":
                    permission_by_check[check] = True
                else:
                    permission_by_check[check] = UserInvalidWorkspacePermissionsError(
                        check.actor, workspace, check.operation_name
                    )

        return permission_by_check

    def get_permissions_object(self, actor, workspace=None, include_trash=False):
        if workspace is None:
            return None

        if include_trash:
            manager = WorkspaceUser.objects_and_trash
        else:
            manager = WorkspaceUser.objects

        queryset = manager.filter(user_id=actor.id, workspace_id=workspace.id)

        try:
            # Check if the user is a member of this workspace
            workspace_user = queryset.get()
        except WorkspaceUser.DoesNotExist:
            return None

        return {
            "admin_only_operations": self.ADMIN_ONLY_OPERATIONS,
            "is_admin": "ADMIN" in workspace_user.permissions,
        }


class StaffOnlySettingOperationPermissionManagerType(PermissionManagerType):
    """
    A permission manager which uses Settings as a way to restrict non-staff
    from performing a specific operations.
    """

    type = "setting_operation"
    supported_actor_types = [UserSubjectType.type]

    # Maps `CoreOperationType` to `Setting` boolean field.
    STAFF_ONLY_SETTING_OPERATION_MAP = {
        CreateWorkspaceOperationType.type: "allow_global_workspace_creation"
    }

    def get_permitted_operations_for_settings(self) -> tuple[list, list]:
        """
        Responsible for returning a tuple, where the first item is a list of
        operations which are permitted because their connecting `Setting` value
        are set to `True`, and the second item is a list of operations which are
        always permitted to staff.

        The combination of these two lists, and the actor's `is_staff` value,
        are to allow the frontend and backend to determine if the actor has the
        necessary permissions for the operations in `STAFF_ONLY_SETTING_OPERATION_MAP`.
        """

        # The lists which contain our always allowed / staff only operations.
        always_allowed_operations = []
        staff_only_operations = []

        # Fetch the instance's Settings.
        settings = CoreHandler().get_settings()

        # Loop over each operation which currently has a Settings page setting.
        for (
            staff_operation_type,
            setting_key,
        ) in self.STAFF_ONLY_SETTING_OPERATION_MAP.items():
            if getattr(settings, setting_key, False):
                always_allowed_operations.append(staff_operation_type)
            else:
                staff_only_operations.append(staff_operation_type)
        return always_allowed_operations, staff_only_operations

    def check_multiple_permissions(self, checks, workspace=None, include_trash=False):
        (always_allowed_ops, staff_only_ops) = local_cache.get(
            "settings", self.get_permitted_operations_for_settings
        )

        result = {}
        for check in checks:
            if check.operation_name in self.STAFF_ONLY_SETTING_OPERATION_MAP:
                if check.operation_name in always_allowed_ops or (
                    check.operation_name in staff_only_ops and check.actor.is_staff
                ):
                    result[check] = True
                else:
                    result[check] = PermissionDenied()

        return result

    def get_permissions_object(self, actor, workspace=None):
        (
            always_allowed_ops,
            staff_only_ops,
        ) = self.get_permitted_operations_for_settings()
        return {
            "staff_only_operations": staff_only_ops,
            "always_allowed_operations": always_allowed_ops,
        }


class ApplicationTypeEnabledPermissionManagerType(PermissionManagerType):
    """
    A permission manager which hides applications whose type has been disabled through
    the instance settings. A disabled type is not deleted: its applications are excluded
    from the listings and every operation on them, or on anything they contain, is
    denied until an administrator enables the type again.

    While every application type is enabled, which is the default, this manager decides
    nothing and never looks at a context.
    """

    type = "application_type_enabled"
    # Every actor type there is: a disabled application type is closed to database API
    # tokens and to user source users just as much as to a signed in user.
    supported_actor_types = [
        UserSubjectType.type,
        AnonymousUserSubjectType.type,
        UserSourceUserSubjectType.type,
        TokenSubjectType.type,
    ]

    def get_disabled_application_types(self) -> List[str]:
        """
        Returns the names of the application types that an administrator disabled
        through the instance settings. The result is cached for the request.
        """

        def get_disabled():
            handler = CoreHandler()
            return [
                application_type.type
                for application_type in application_type_registry.get_all()
                if not handler.application_type_is_enabled(application_type.type)
            ]

        return local_cache.get("disabled_application_types", get_disabled)

    def _get_disabled_content_type_ids(self, disabled: List[str]) -> List[int]:
        """
        Returns the content type ids of the provided disabled application types.
        """

        models = [
            application_type_registry.get(type_name).model_class
            for type_name in disabled
        ]
        return [
            content_type.id
            for content_type in ContentType.objects.get_for_models(*models).values()
        ]

    def _operation_happens_in_an_application(self, operation_name: str) -> bool:
        """
        Whether the context of the given operation is an application, or something an
        application contains. Depends only on the registries, so it is cached for the
        request.
        """

        def resolve():
            application_scope = object_scope_type_registry.get(
                ApplicationObjectScopeType.type
            )
            return object_scope_type_registry.scope_type_includes_scope_type(
                application_scope,
                operation_type_registry.get(operation_name).context_scope,
            )

        return local_cache.get(f"operation_in_application_{operation_name}", resolve)

    def _get_application_type(self, check) -> Optional[str]:
        """
        Resolves the type of the application the given check operates on, by walking
        the scope hierarchy up from the check context. Returns `None` when the
        operation doesn't happen inside an application at all.

        The answer is cached per context for the request, so a batch of checks on the
        same object walks the hierarchy once.
        """

        context = check.context

        if context is None or not self._operation_happens_in_an_application(
            check.operation_name
        ):
            return None

        def resolve():
            application = object_scope_type_registry.get_parent(
                context, at_scope_type=ApplicationObjectScopeType
            )
            return application_type_registry.get_by_model(
                application.specific_class
            ).type

        return local_cache.get(
            f"application_type_of_{type(context).__name__}_{context.pk}", resolve
        )

    def check_multiple_permissions(self, checks, workspace=None, include_trash=False):
        disabled = self.get_disabled_application_types()

        if not disabled:
            return {}

        result = {}
        for check in checks:
            if self._get_application_type(check) in disabled:
                result[check] = PermissionDenied()

        return result

    # No `get_permissions_object`: the frontend already reads the `enable_<type>`
    # settings straight from the settings store, so there is nothing to send it here.

    def filter_queryset(self, actor, operation_name, queryset, workspace=None):
        if operation_name != ListApplicationsWorkspaceOperationType.type:
            return None

        disabled = self.get_disabled_application_types()

        if not disabled:
            return None

        return queryset.exclude(
            content_type_id__in=self._get_disabled_content_type_ids(disabled)
        )
