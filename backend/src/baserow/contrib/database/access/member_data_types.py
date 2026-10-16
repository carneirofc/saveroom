from typing import List

from django.contrib.auth.models import AbstractUser

from rest_framework import serializers

from baserow.api.user.registries import MemberDataType
from baserow.core.handler import CoreHandler
from baserow.core.models import Workspace

from .models import ACCESS_LEVELS, DatabaseAccessGrant
from .operations import ManageDatabaseAccessWorkspaceOperationType


class DefaultAccessMemberDataType(MemberDataType):
    """
    Adds the workspace default access level granted directly to every member to the
    workspace members listing. `None` means the member inherits, or that the actor
    can't manage access.
    """

    type = "access_level"

    def get_request_serializer_field(self) -> serializers.Field:
        return serializers.ChoiceField(
            choices=ACCESS_LEVELS,
            required=False,
            allow_null=True,
            help_text="The workspace default access level set directly on the "
            "member, or null when the member inherits it.",
        )

    def annotate_serialized_workspace_members_data(
        self, workspace: Workspace, serialized_data: List[dict], user: AbstractUser
    ) -> List[dict]:
        levels = {}
        can_manage = user.is_staff or CoreHandler().check_permissions(
            user,
            ManageDatabaseAccessWorkspaceOperationType.type,
            workspace=workspace,
            context=workspace,
            raise_permission_exceptions=False,
        )
        if can_manage:
            levels = dict(
                DatabaseAccessGrant.objects.filter(
                    workspace=workspace,
                    database__isnull=True,
                    table__isnull=True,
                    user_id__in=[member["user_id"] for member in serialized_data],
                ).values_list("user_id", "level")
            )

        for member in serialized_data:
            member[self.type] = levels.get(member["user_id"])
        return serialized_data

    def annotate_serialized_admin_users_data(
        self, user_ids: List[int], serialized_data: List[dict], user: AbstractUser
    ) -> List[dict]:
        return serialized_data
