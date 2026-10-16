from django.utils.functional import lazy

from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from baserow.contrib.database.api.data_sync.serializers import DataSyncSerializer
from baserow.contrib.database.fields.registries import field_type_registry
from baserow.contrib.database.rows.constants import (
    IMPORT_MATCHING_MODES,
    IMPORT_MODE_INSERT,
    IMPORT_MODE_UPSERT,
    IMPORT_MODES,
)
from baserow.contrib.database.table.models import Table


class TableImportConfiguration(serializers.Serializer):
    """
    Additional table import configuration.
    """

    upsert_fields = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        min_length=1,
        allow_null=True,
        allow_empty=True,
        default=None,
        help_text=lazy(
            lambda: (
                "A list of field IDs in the table used to generate a value for "
                "identifying a row during the upsert process in file import. Each "
                "field ID must reference an existing field in the table, which will "
                "be used to match provided values against existing ones to determine "
                "whether a row should be inserted or updated.\n "
                "Field types that can be used in upsert fields: "
                f"{','.join([f.type for f in field_type_registry.get_all() if f.can_upsert])}. "
                "If specified, `upsert_values` should also be provided."
            )
        ),
    )
    upsert_values = serializers.ListField(
        allow_empty=True,
        allow_null=True,
        default=None,
        child=serializers.ListField(
            min_length=1,
        ),
        help_text=(
            "A list of values that are identifying rows in imported data.\n "
            "The number of rows in `upsert_values` should be equal to the number of "
            "rows in imported data. Each row in `upsert_values` should contain a "
            "list of values that match the number and field types of fields selected "
            "in `upsert_fields`. Based on `upsert_fields`, a similar upsert values "
            "will be calculated for each row in the table.\n "
            "There's no guarantee of uniqueness of row identification calculated from "
            "`upsert_values` nor from the table. Repeated upsert values are compared "
            "in order with matching values in the table. The imported data must be in "
            "the same order as the table rows for correct matching."
        ),
    )
    skipped_fields = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        allow_null=True,
        allow_empty=True,
        default=None,
        help_text="A list of field IDs that should not be overwritten during upsert operations.",
    )
    mode = serializers.ChoiceField(
        choices=IMPORT_MODES,
        required=False,
        allow_null=True,
        default=None,
        help_text=(
            "How the imported rows are applied to the table. `insert` appends every "
            "row. `upsert` updates the rows matching `upsert_fields` and inserts the "
            "others. `update` only updates the matching rows. `replace` trashes every "
            "existing row before inserting. Defaults to `upsert` when `upsert_fields` "
            "is provided, otherwise `insert`."
        ),
    )
    delete_unmatched = serializers.BooleanField(
        required=False,
        default=False,
        help_text=(
            "Only with `upsert` or `update`: trash the existing rows that are not "
            "matched by any imported row."
        ),
    )
    allow_ambiguous_matches = serializers.BooleanField(
        required=False,
        default=False,
        help_text=(
            "When the match keys are not unique in the imported data or in the table, "
            "the import is refused unless this is true. In that case duplicates are "
            "paired in order."
        ),
    )

    def validate(self, attrs):
        if attrs.get("upsert_fields") and not len(attrs.get("upsert_values") or []):
            raise ValidationError(
                {
                    "upsert_value": (
                        "upsert_values must not be empty "
                        "when upsert_fields are provided."
                    )
                }
            )

        if not attrs.get("mode"):
            # Imports without an explicit mode keep pairing duplicates in order.
            attrs["allow_ambiguous_matches"] = True
        mode = attrs.get("mode") or (
            IMPORT_MODE_UPSERT if attrs.get("upsert_fields") else IMPORT_MODE_INSERT
        )
        attrs["mode"] = mode

        if mode in IMPORT_MATCHING_MODES and not attrs.get("upsert_fields"):
            raise ValidationError(
                {"upsert_fields": f"upsert_fields are required with the `{mode}` mode."}
            )
        if mode not in IMPORT_MATCHING_MODES and attrs.get("upsert_fields"):
            raise ValidationError(
                {
                    "upsert_fields": f"upsert_fields can't be used with the `{mode}` mode."
                }
            )
        if attrs.get("delete_unmatched") and mode not in IMPORT_MATCHING_MODES:
            raise ValidationError(
                {
                    "delete_unmatched": (
                        "delete_unmatched can only be used with the `upsert` or "
                        "`update` mode."
                    )
                }
            )
        return attrs


class TableSerializer(serializers.ModelSerializer):
    data_sync = DataSyncSerializer()

    class Meta:
        model = Table
        fields = (
            "id",
            "name",
            "order",
            "database_id",
            "require_edit_confirmation",
            "data_sync",
        )
        extra_kwargs = {
            "id": {"read_only": True},
            "database_id": {"read_only": True},
            "order": {"help_text": "Lowest first."},
        }


class TableWithoutDataSyncSerializer(TableSerializer):
    data_sync = None

    class Meta(TableSerializer.Meta):
        fields = (
            "id",
            "name",
            "order",
            "database_id",
            "require_edit_confirmation",
        )


class TableCreateSerializer(serializers.ModelSerializer):
    data = serializers.ListField(
        min_length=1,
        default=None,
        child=serializers.ListField(allow_empty=False),
        help_text=(
            "A list of rows that needs to be created as initial table data. "
            "Each row is a list of values that are going to be added in the new "
            "table in the same order as provided.\n\n"
            'Ex: \n```json\n[\n  ["row1_field1_value", "row1_field2_value"],\n'
            '  ["row2_field1_value", "row2_field2_value"],\n]\n```\n'
            "for creating a two rows table with two fields.\n\n"
            "If not provided, some example data is going to be created."
        ),
    )
    first_row_header = serializers.BooleanField(
        default=False,
        help_text="Indicates if the first provided row is the header. If true the "
        "field names are going to be the values of the first row. Otherwise "
        'they will be called "Field N"',
    )
    importer_type = serializers.CharField(
        max_length=32,
        required=False,
        allow_blank=True,
        default="",
        help_text="The frontend importer identifier used to parse the file.",
    )
    original_file_name = serializers.CharField(
        max_length=255,
        required=False,
        allow_blank=True,
        default="",
        help_text="The original name of the uploaded file.",
    )

    class Meta:
        model = Table
        fields = (
            "name",
            "data",
            "first_row_header",
            "importer_type",
            "original_file_name",
        )
        extra_kwargs = {
            "data": {"required": False},
            "first_row_header": {"required": False},
        }


class TableImportSerializer(serializers.Serializer):
    data = serializers.ListField(
        min_length=1,
        required=True,
        child=serializers.ListField(allow_empty=False),
        help_text=(
            "A list of rows you want to add to the specified table. "
            "Each row is a list of values, one for each **writable** field. "
            "The field values must be ordered according to the field order in the "
            "table. "
            "All values must be compatible with the corresponding field type.\n\n"
            'Ex: \n```json\n[\n  ["row1_field1_value", "row1_field2_value"],\n'
            '  ["row2_field1_value", "row2_field2_value"],\n]\n```\n'
            "for adding two rows to a table with two writable fields."
        ),
    )
    configuration = TableImportConfiguration(required=False, default=None)
    importer_type = serializers.CharField(
        max_length=32,
        required=False,
        allow_blank=True,
        default="",
        help_text="The frontend importer identifier used to parse the file.",
    )
    original_file_name = serializers.CharField(
        max_length=255,
        required=False,
        allow_blank=True,
        default="",
        help_text="The original name of the uploaded file.",
    )

    class Meta:
        fields = ("data", "importer_type", "original_file_name")

    def validate(self, attrs):
        if attrs.get("configuration"):
            if attrs["configuration"].get("upsert_values"):
                if len(attrs["configuration"].get("upsert_values")) != len(
                    attrs["data"]
                ):
                    msg = (
                        "`data` and `configuration.upsert_values` "
                        "should have the same length."
                    )
                    raise ValidationError(
                        {"data": msg, "configuration": {"upsert_values": msg}}
                    )
        return attrs


class TableImportPreviewSerializer(TableImportSerializer):
    sample_size = serializers.IntegerField(
        min_value=0,
        max_value=200,
        default=50,
        help_text="The maximum number of rows returned for each kind of change.",
    )


class TableImportPreviewUpdateSerializer(serializers.Serializer):
    import_index = serializers.IntegerField(
        help_text="The index of the row in the imported `data`."
    )
    row = serializers.DictField(help_text="The existing row before the import.")
    changed_field_ids = serializers.ListField(child=serializers.IntegerField())


class TableImportPreviewAmbiguousKeySerializer(serializers.Serializer):
    values = serializers.ListField(
        child=serializers.CharField(allow_null=True),
        help_text="The values of the match fields, in `upsert_fields` order.",
    )
    file_count = serializers.IntegerField()
    table_count = serializers.IntegerField()


class TableImportPreviewResponseSerializer(serializers.Serializer):
    summary = serializers.DictField(
        child=serializers.IntegerField(),
        help_text=(
            "The number of rows the import would `create`, `update`, leave "
            "`unchanged`, `delete`, `skip`, and the rows in `errors`."
        ),
    )
    ambiguous_blocked = serializers.BooleanField(
        help_text=(
            "True if the import would be refused because of ambiguous match keys."
        )
    )
    ambiguous = TableImportPreviewAmbiguousKeySerializer(many=True)
    create = serializers.ListField(
        child=serializers.IntegerField(),
        help_text="Indexes in `data` of the rows that would be created.",
    )
    update = TableImportPreviewUpdateSerializer(many=True)
    delete = serializers.ListField(
        child=serializers.DictField(), help_text="The rows that would be trashed."
    )
    skipped = serializers.ListField(
        child=serializers.IntegerField(),
        help_text="Indexes in `data` of the unmatched rows the `update` mode ignores.",
    )
    errors = serializers.DictField(
        child=serializers.DictField(),
        help_text="Validation errors by index in `data`.",
    )


class TableUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Table
        fields = ("name", "require_edit_confirmation")
        extra_kwargs = {
            "name": {"required": False},
            "require_edit_confirmation": {"required": False},
        }

    def validate(self, attrs):
        if not attrs:
            raise ValidationError(
                "At least one of name or require_edit_confirmation must be provided."
            )
        return attrs


class OrderTablesSerializer(serializers.Serializer):
    table_ids = serializers.ListField(
        child=serializers.IntegerField(), help_text="Table ids in the desired order."
    )
