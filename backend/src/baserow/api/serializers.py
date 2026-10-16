from urllib.parse import quote, urljoin

from django.conf import settings
from django.urls import reverse

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from rest_framework.relations import PrimaryKeyRelatedField

from baserow.api.download.tokens import sign_download_token
from baserow.core.context import clear_current_workspace_id, set_current_workspace_id
from baserow.core.storage import get_default_storage
from baserow.core.utils import split_comma_separated_string


class PrefetchedManyToManyListSerializer(serializers.ListSerializer):
    """
    Reads a many-to-many relation straight from the instance's prefetch cache
    instead of going through `getattr(instance, field)`, which builds a Django
    `ManyRelatedManager` for every row. For wide tables serialized in bulk this
    manager creation dominates the response time. Falls back to the default
    lookup when the relation wasn't prefetched.

    Use as `Meta.list_serializer_class` on a serializer used with `many=True`.
    """

    def get_attribute(self, instance):
        prefetched = getattr(instance, "_prefetched_objects_cache", None)
        if prefetched is not None and len(self.source_attrs) == 1:
            cached = prefetched.get(self.source_attrs[0])
            if cached is not None:
                return cached
        return super().get_attribute(instance)


def get_example_pagination_serializer_class(
    results_serializer_class,
    additional_fields=None,
    serializer_name=None,
):
    """
    Generates a pagination like response serializer that has the provided serializer
    class as results. It is only used for example purposes in combination with the
    openapi documentation.

    :param results_serializer_class: The serializer class that needs to be added as
        results.
    :type results_serializer_class: Serializer
    :param additional_fields: A dict containing additional fields that must be added
        to the serializer. The fields are going to be placed at the root of the
        serializer.
    :type additional_fields: dict
    :param serializer_name: The class name of the serializer. Generated serializer
        should be unique because serializer with the same class name are reused.
    :type serializer_name: str
    :return: The generated pagination serializer.
    :rtype: Serializer
    """

    fields = {
        "count": serializers.IntegerField(help_text="The total amount of results."),
        "next": serializers.URLField(
            allow_blank=True, allow_null=True, help_text="URL to the next page."
        ),
        "previous": serializers.URLField(
            allow_blank=True, allow_null=True, help_text="URL to the previous page."
        ),
        "results": results_serializer_class(many=True),
    }

    if additional_fields:
        fields.update(**additional_fields)

    if not serializer_name:
        serializer_name = "PaginationSerializer"

    return type(
        serializer_name + results_serializer_class.__name__,
        (serializers.Serializer,),
        fields,
    )


class NaturalKeyRelatedField(serializers.ListField):
    """
    A related field that use the natural key instead of the Id to reference the object.
    """

    def __init__(
        self, model=None, custom_does_not_exist_exception_class=None, **kwargs
    ):
        self._model = model
        self._custom_does_not_exist_exception_class = (
            custom_does_not_exist_exception_class
        )
        super().__init__(**kwargs)

    def to_representation(self, value):
        representation = super().to_representation(value.natural_key())

        if len(representation) == 1:
            return representation[0]
        else:
            return representation

    def to_internal_value(self, data):
        if not isinstance(data, list):
            data = [data]

        natural_key = super().to_internal_value(data)
        try:
            return self.get_queryset().get_by_natural_key(*natural_key)
        except self._model.DoesNotExist as e:
            if self._custom_does_not_exist_exception_class:
                raise self._custom_does_not_exist_exception_class(
                    f"Object with natural key {natural_key} for model {self._model} does not exist."
                )
            else:
                raise e

    def get_queryset(self):
        return self._model.objects


class CommaSeparatedIntegerValuesField(serializers.Field):
    """A serializer field that accepts a CSV string containing a list of integers."""

    def to_representation(self, value):
        return ",".join(value)

    def to_internal_value(self, data):
        try:
            record_ids = split_comma_separated_string(data)
        except ValueError as e:
            raise serializers.ValidationError(str(e), code="invalid") from e
        if not all([record.isdigit() for record in record_ids]):
            raise serializers.ValidationError("The provided record ids are not valid.")

        return record_ids


class FileURLSerializerMixin(serializers.Serializer):
    """
    Adds the two links to an exported file: `download_url`, which goes through this
    API, and the older `url`, which points straight at the storage.

    `download_url` exists because the storage URL is not reachable from a browser in
    most container deployments: with a volume it resolves to a `/media/` path nothing
    serves, and with object storage it is a presigned link to an address that is often
    only routable inside the cluster. Streaming through the API works everywhere.
    """

    url = serializers.SerializerMethodField(
        help_text=(
            "DEPRECATED: use download_url instead. A link straight to the file in the "
            "server's storage. It is only reachable when that storage is exposed to "
            "the client, which is not the case for a volume backed deployment or for "
            "a bucket that is private to the cluster."
        )
    )
    download_url = serializers.SerializerMethodField(
        help_text=(
            "A link that downloads the file through this API, streamed out of the "
            "server's storage. It carries a short lived signed token so that a plain "
            "browser link works, and is null while there is no file."
        )
    )

    def get_handler(self):
        """Define handler used for url generation.
        That handler needs to to implement method `export_file_path`.
        """

        raise NotImplementedError("Subclasses must implement this method.")

    def get_instance_attr(self, instance, name):
        return getattr(instance, name)

    @extend_schema_field(OpenApiTypes.URI)
    def get_url(self, instance):
        if hasattr(instance, "workspace_id"):
            # FIXME: Temporarily setting the current workspace ID for URL generation in
            # storage backends, enabling permission checks at download time.
            try:
                set_current_workspace_id(instance.workspace_id)
                return self._get_url(instance)
            finally:
                clear_current_workspace_id()
        else:
            return self._get_url(instance)

    @extend_schema_field(OpenApiTypes.URI)
    def get_download_url(self, instance):
        if not self._get_exported_file_name(instance):
            return None

        download_type, object_id = self.get_download_token_scope(instance)
        path = reverse(
            self.get_download_url_name(), kwargs=self.get_download_url_kwargs(instance)
        )
        # These serializers are also built without a request -- from a celery task
        # broadcasting a finished job, for instance -- so the absolute URL comes from
        # the configured public backend URL rather than from the request.
        url = urljoin(settings.PUBLIC_BACKEND_URL, path)
        token = sign_download_token(instance.user_id, download_type, object_id)
        return f"{url}?token={quote(token)}"

    def get_download_url_name(self) -> str:
        """The name of the url pattern serving this kind of download."""

        raise NotImplementedError("Subclasses must implement this method.")

    def get_download_url_kwargs(self, instance) -> dict:
        """The url kwargs identifying the file within that pattern."""

        raise NotImplementedError("Subclasses must implement this method.")

    def get_download_token_scope(self, instance):
        """
        The download type and object id the token is bound to, so that a link minted
        for one file cannot be replayed against another.
        """

        raise NotImplementedError("Subclasses must implement this method.")

    def _get_exported_file_name(self, instance):
        return self.get_instance_attr(instance, "exported_file_name")

    def _get_url(self, instance):
        handler = self.get_handler()
        name = self._get_exported_file_name(instance)

        if not name:
            return None

        path = handler.export_file_path(name)
        storage = get_default_storage()
        return storage.url(path)


class NonValidatingPrimaryKeyRelatedField(PrimaryKeyRelatedField):
    def get_queryset(self):
        return None

    def to_representation(self, value):
        if isinstance(value, int):
            return value
        else:
            return value.pk

    def to_internal_value(self, data):
        try:
            return int(data)
        except ValueError, TypeError:
            raise ValidationError(f"Invalid ID: {data}")
