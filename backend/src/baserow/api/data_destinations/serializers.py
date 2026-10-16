from rest_framework import serializers

from baserow.core.data_destinations.config import ALL_PURPOSES


class DataDestinationSerializer(serializers.Serializer):
    name = serializers.CharField(help_text="The name destinations are referenced by.")
    type = serializers.CharField(
        help_text="The kind of storage: s3, azure or filesystem."
    )
    purposes = serializers.ListField(
        child=serializers.ChoiceField(choices=ALL_PURPOSES),
        help_text="What the destination may be used for.",
    )
    allow_trust_public_key = serializers.BooleanField(
        help_text=(
            "Whether staff may trust the signing key of a backup made by another "
            "instance when restoring from this destination."
        ),
    )
