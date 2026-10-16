from rest_framework import serializers

from baserow.core.teams.models import Team, TeamMember


class TeamMemberSerializer(serializers.ModelSerializer):
    user_id = serializers.IntegerField(read_only=True)
    name = serializers.CharField(source="user.first_name", read_only=True)
    email = serializers.EmailField(source="user.email", read_only=True)

    class Meta:
        model = TeamMember
        fields = ("id", "user_id", "name", "email", "source")


class TeamSerializer(serializers.ModelSerializer):
    workspace_id = serializers.IntegerField(read_only=True)
    members = TeamMemberSerializer(many=True, read_only=True)

    class Meta:
        model = Team
        fields = ("id", "workspace_id", "name", "members", "created_on")


class CreateTeamSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=255)
    user_ids = serializers.ListField(
        child=serializers.IntegerField(), required=False, default=list
    )


class UpdateTeamSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=255)


class TeamMembersSerializer(serializers.Serializer):
    user_ids = serializers.ListField(child=serializers.IntegerField(), min_length=1)
