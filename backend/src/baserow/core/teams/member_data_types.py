from collections import defaultdict
from typing import List

from django.contrib.auth.models import AbstractUser

from rest_framework import serializers

from baserow.api.user.registries import MemberDataType
from baserow.core.models import Workspace

from .models import TeamMember


class TeamsMemberDataType(MemberDataType):
    """Adds the teams of every member to the workspace members listing."""

    type = "teams"

    def get_request_serializer_field(self) -> serializers.Field:
        return serializers.ListField(
            child=serializers.DictField(),
            required=False,
            help_text="The teams of the member in this workspace, as `id` and `name`.",
        )

    def annotate_serialized_workspace_members_data(
        self, workspace: Workspace, serialized_data: List[dict], user: AbstractUser
    ) -> List[dict]:
        user_ids = [member["user_id"] for member in serialized_data]
        teams_by_user = defaultdict(list)
        memberships = (
            TeamMember.objects.filter(team__workspace=workspace, user_id__in=user_ids)
            .select_related("team")
            .order_by("team__name", "team_id")
        )
        for membership in memberships:
            teams_by_user[membership.user_id].append(
                {"id": membership.team_id, "name": membership.team.name}
            )

        for member in serialized_data:
            member[self.type] = teams_by_user.get(member["user_id"], [])
        return serialized_data

    def annotate_serialized_admin_users_data(
        self, user_ids: List[int], serialized_data: List[dict], user: AbstractUser
    ) -> List[dict]:
        return serialized_data
