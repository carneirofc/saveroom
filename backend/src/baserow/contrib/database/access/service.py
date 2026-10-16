from typing import Dict, List

from django.contrib.auth.models import AbstractUser

from baserow.core.handler import CoreHandler

from .handler import AccessScope, DatabaseAccessHandler
from .operations import ManageDatabaseAccessWorkspaceOperationType


class DatabaseAccessService:
    """
    Permission-aware management of access grants. Workspace admins manage their own
    workspaces; staff manage any workspace, member or not.
    """

    def __init__(self):
        self.handler = DatabaseAccessHandler()

    def _check(self, user: AbstractUser, scope: AccessScope):
        if user.is_staff:
            return
        CoreHandler().check_permissions(
            user,
            ManageDatabaseAccessWorkspaceOperationType.type,
            workspace=scope.workspace,
            context=scope.workspace,
        )

    def get_scope(self, user: AbstractUser, scope_type: str, scope_id: int):
        scope = self.handler.get_scope(scope_type, scope_id)
        self._check(user, scope)
        return scope

    def set_grants(
        self, user: AbstractUser, scope: AccessScope, grants: List[Dict]
    ) -> None:
        self._check(user, scope)
        self.handler.set_grants(scope, grants)
