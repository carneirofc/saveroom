from typing import List

from django.contrib.auth.models import AbstractUser

from rest_framework import serializers

from baserow.core.models import Workspace
from baserow.core.registries import WorkspaceUsersAddOptionType

from .handler import SCOPE_WORKSPACE, AccessScope
from .models import ACCESS_LEVELS
from .service import DatabaseAccessService


class DefaultAccessLevelAddOptionType(WorkspaceUsersAddOptionType):
    """
    Gives the users being added a workspace default access level, so an admin can add
    people who are restricted from the start.
    """

    type = "access_level"

    def get_serializer_field(self) -> serializers.Field:
        return serializers.ChoiceField(
            choices=ACCESS_LEVELS,
            required=False,
            allow_null=True,
            default=None,
            help_text="The workspace default access level the users get. Omit or null "
            "to let them inherit full member access.",
        )

    def apply(
        self,
        actor: AbstractUser,
        workspace: Workspace,
        users: List[AbstractUser],
        value: str,
    ) -> None:
        DatabaseAccessService().set_grants(
            actor,
            AccessScope(SCOPE_WORKSPACE, workspace),
            [
                {"subject_type": "user", "subject_id": user.id, "level": value}
                for user in users
            ],
        )
