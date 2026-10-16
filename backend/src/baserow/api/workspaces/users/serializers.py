from django.contrib.auth import get_user_model

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from baserow.api.mixins import UnknownFieldRaisesExceptionSerializerMixin
from baserow.api.two_factor_auth.serializers import TwoFactorAuthSerializer
from baserow.api.user.registries import member_data_registry
from baserow.core.models import WorkspaceUser
from baserow.core.registries import workspace_users_add_option_registry

User = get_user_model()


class WorkspaceUserSerializer(serializers.ModelSerializer):
    name = serializers.SerializerMethodField(help_text="User defined name.")
    email = serializers.SerializerMethodField(help_text="User email.")
    to_be_deleted = serializers.BooleanField(
        source="user.profile.to_be_deleted",
        help_text="True if user account is pending deletion.",
    )
    two_factor_auth = serializers.SerializerMethodField()

    class Meta:
        model = WorkspaceUser
        fields = (
            "id",
            "name",
            "email",
            "workspace",
            "permissions",
            "created_on",
            "user_id",
            "to_be_deleted",
            "two_factor_auth",
        )

    @extend_schema_field(OpenApiTypes.STR)
    def get_name(self, object):
        return object.user.first_name

    @extend_schema_field(OpenApiTypes.STR)
    def get_email(self, object):
        return object.user.email

    def get_two_factor_auth(self, object):
        try:
            provider = object.user.two_factor_auth_provider
        except User.two_factor_auth_provider.RelatedObjectDoesNotExist:
            provider = None

        return TwoFactorAuthSerializer(provider).data


def get_member_data_types_request_serializer():
    """
    Responsible for iterating over all data types registered to `MemberDataRegistry`,
    building a dictionary of `data_type.type` and the data type's serializer field,
    and creating a new serializer with those attributes.

    The resulting serializer will be inherited by
    `ListWorkspaceUsersWithMemberDataSerializer`.
    """

    attrs = {}

    for data_type in member_data_registry.get_all():
        field = data_type.get_request_serializer_field()
        if isinstance(field, serializers.Field):
            attrs[data_type.type] = field
        else:
            for key, field in field.items():
                attrs[key] = field

    class Meta:
        fields = tuple(attrs.keys())

    attrs["Meta"] = Meta

    return type(
        "MemberDataTypeSerializer",
        (UnknownFieldRaisesExceptionSerializerMixin, serializers.Serializer),
        attrs,
    )


def get_list_workspace_user_serializer():
    """
    Returns a list serializer for the `WorkspaceUser` model.

    It's dynamically generated so that we can include fields via the
    `MemberDataRegistry`.
    """

    MemberDataTypeSerializer = get_member_data_types_request_serializer()

    class ListWorkspaceUsersWithMemberDataSerializer(
        MemberDataTypeSerializer, WorkspaceUserSerializer
    ):
        class Meta(WorkspaceUserSerializer.Meta):
            fields = (
                WorkspaceUserSerializer.Meta.fields
                + MemberDataTypeSerializer.Meta.fields
            )

    return ListWorkspaceUsersWithMemberDataSerializer


class WorkspaceUserWorkspaceSerializer(serializers.Serializer):
    """
    This serializers includes relevant fields of the Workspace model, but also
    some WorkspaceUser specific fields related to the workspace user relation.

    Additionally, the list of users are included for each workspace.
    """

    # Workspace fields
    id = serializers.IntegerField(
        source="workspace.id", read_only=True, help_text="Workspace id."
    )
    name = serializers.CharField(
        source="workspace.name", read_only=True, help_text="Workspace name."
    )
    users = WorkspaceUserSerializer(
        many=True,
        source="workspace.workspaceuser_set",
        required=False,
        read_only=True,
        help_text="List of all workspace users.",
    )

    # WorkspaceUser fields
    order = serializers.IntegerField(
        read_only=True,
        help_text="The requesting user's order within the workspace users.",
    )
    permissions = serializers.CharField(
        read_only=True, help_text="The requesting user's permissions for the workspace."
    )
    unread_notifications_count = serializers.IntegerField(
        read_only=True,
        help_text="The number of unread notifications for the requesting user.",
    )


class UpdateWorkspaceUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = WorkspaceUser
        fields = ("permissions",)


class AddWorkspaceUsersSerializer(serializers.Serializer):
    user_ids = serializers.ListField(
        child=serializers.IntegerField(), min_length=1, max_length=100
    )
    permissions = serializers.ChoiceField(
        choices=["ADMIN", "MEMBER"],
        default="MEMBER",
        help_text="The permissions the added users get in the workspace.",
    )
    team_ids = serializers.ListField(
        child=serializers.IntegerField(),
        required=False,
        default=list,
        max_length=100,
        help_text="Teams of the workspace the users join.",
    )


def get_add_workspace_users_serializer():
    """
    Returns `AddWorkspaceUsersSerializer` extended with the field of every registered
    `WorkspaceUsersAddOptionType`. It's built when used because apps register their
    options after this module is imported.
    """

    attrs = {
        option_type.type: option_type.get_serializer_field()
        for option_type in workspace_users_add_option_registry.get_all()
    }
    return type(
        "AddWorkspaceUsersWithOptionsSerializer", (AddWorkspaceUsersSerializer,), attrs
    )


class WorkspaceUserCandidateSerializer(serializers.ModelSerializer):
    user_id = serializers.IntegerField(source="id")
    name = serializers.CharField(source="first_name")

    class Meta:
        model = User
        fields = ("user_id", "name", "email")


class WorkspaceUserCandidatesQuerySerializer(serializers.Serializer):
    search = serializers.CharField(min_length=3, max_length=255)


class GetWorkspaceUsersViewParamsSerializer(serializers.Serializer):
    search = serializers.CharField(required=False, allow_null=True, default=None)
    sorts = serializers.CharField(required=False, allow_null=True, default=None)
