from rest_framework import serializers


class AdminBuildInfoSerializer(serializers.Serializer):
    """
    Identifies the source this instance was built from. The values come from
    build arguments baked into the image, so they are empty in a development
    checkout and every field is allowed to be blank.
    """

    version = serializers.CharField(
        allow_blank=True,
        help_text="The release tag this instance was built from, empty for a "
        "development build.",
    )
    commit = serializers.CharField(
        allow_blank=True,
        help_text="The full git commit hash this instance was built from, empty "
        "for a development build.",
    )
    build_date = serializers.CharField(
        allow_blank=True,
        help_text="When the image was built, as an ISO 8601 timestamp. Empty for a "
        "development build.",
    )
    baserow_version = serializers.CharField(
        help_text="The version of the Baserow codebase this fork tracks."
    )
