from rest_framework import serializers

from baserow.core.api_clients.models import ApiClient, ApiClientKey
from baserow.core.api_clients.scopes import ALL_SCOPES


class ApiClientKeySerializer(serializers.ModelSerializer):
    is_usable = serializers.BooleanField(read_only=True)

    class Meta:
        model = ApiClientKey
        fields = (
            "id",
            "name",
            "prefix",
            "created_on",
            "last_used_on",
            "expires_on",
            "revoked_on",
            "is_usable",
        )
        read_only_fields = fields


class ApiClientSerializer(serializers.ModelSerializer):
    keys = ApiClientKeySerializer(many=True, read_only=True)

    class Meta:
        model = ApiClient
        fields = (
            "id",
            "name",
            "workspace",
            "scopes",
            "is_active",
            "created_on",
            "updated_on",
            "keys",
        )
        read_only_fields = fields


class CreateApiClientSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=100)
    scopes = serializers.ListField(
        child=serializers.ChoiceField(choices=ALL_SCOPES),
        allow_empty=True,
        help_text=(
            "The scopes requests made with this client are limited to. "
            f"Valid scopes are: {', '.join(ALL_SCOPES)}."
        ),
    )


class UpdateApiClientSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=100, required=False)
    scopes = serializers.ListField(
        child=serializers.ChoiceField(choices=ALL_SCOPES),
        allow_empty=True,
        required=False,
    )
    is_active = serializers.BooleanField(required=False)


class CreateApiClientKeySerializer(serializers.Serializer):
    name = serializers.CharField(max_length=100, required=False, allow_blank=True)
    expires_on = serializers.DateTimeField(
        required=False,
        allow_null=True,
        help_text="After this moment the key stops working. Null never expires.",
    )


class CreatedApiClientKeySerializer(ApiClientKeySerializer):
    key = serializers.CharField(
        read_only=True,
        help_text=(
            "The full key to authenticate with, in the form `prefix.secret`. Only the "
            "hash of the secret is stored, so this is the one and only time it is "
            "returned. Store it now."
        ),
    )

    class Meta(ApiClientKeySerializer.Meta):
        fields = ApiClientKeySerializer.Meta.fields + ("key",)
        read_only_fields = fields
