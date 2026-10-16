from rest_framework import serializers

from baserow.contrib.database.access.handler import SUBJECT_TYPES
from baserow.contrib.database.access.models import ACCESS_LEVELS


class AccessSubjectSerializer(serializers.Serializer):
    subject_type = serializers.ChoiceField(choices=SUBJECT_TYPES)
    subject_id = serializers.IntegerField()
    name = serializers.CharField()
    email = serializers.EmailField(required=False, allow_null=True)
    is_admin = serializers.BooleanField()
    level = serializers.ChoiceField(choices=ACCESS_LEVELS, allow_null=True)
    inherited_level = serializers.ChoiceField(choices=ACCESS_LEVELS, allow_null=True)
    inherited_from = serializers.CharField(allow_null=True)


class ScopeAccessSerializer(serializers.Serializer):
    scope_type = serializers.CharField()
    scope_id = serializers.IntegerField()
    workspace_id = serializers.IntegerField()
    subjects = AccessSubjectSerializer(many=True)


class GrantSerializer(serializers.Serializer):
    subject_type = serializers.ChoiceField(choices=SUBJECT_TYPES)
    subject_id = serializers.IntegerField()
    level = serializers.ChoiceField(
        choices=ACCESS_LEVELS,
        allow_null=True,
        help_text="The access level, or null to remove the grant and inherit again.",
    )


class SetGrantsSerializer(serializers.Serializer):
    grants = GrantSerializer(many=True)
