"""
Maps Baserow field types to Parquet (Arrow) column types.

Every field type gets a typed column where the value has a natural Arrow shape, so a
datalake can query it without parsing. Anything without a dedicated mapper falls back
to a JSON string of the field's rich export value, which keeps new or plugin field
types exportable without changes here.
"""

import json
from datetime import date, datetime, timedelta
from datetime import timezone as dt_timezone
from typing import TYPE_CHECKING, Any, Optional

import pyarrow as pa

from baserow.core.registry import Instance, Registry

if TYPE_CHECKING:
    from baserow.contrib.database.fields.models import Field
    from baserow.contrib.database.fields.registries import FieldObject

# Parquet readers such as Spark and DuckDB only support decimals up to 38 digits.
DECIMAL_PRECISION = 38
TIMESTAMP_TYPE = pa.timestamp("us", tz="UTC")

SELECT_OPTION_TYPE = pa.struct(
    [("id", pa.int64()), ("value", pa.string()), ("color", pa.string())]
)
LINKED_ROW_TYPE = pa.struct([("id", pa.int64()), ("value", pa.string())])
USER_TYPE = pa.struct([("id", pa.int64()), ("name", pa.string())])
FILE_TYPE = pa.struct(
    [
        ("name", pa.string()),
        ("visible_name", pa.string()),
        ("size", pa.int64()),
        ("mime_type", pa.string()),
        ("is_image", pa.bool_()),
        ("uploaded_at", pa.string()),
    ]
)


def _decimal_type(decimal_places: Optional[int]) -> pa.DataType:
    scale = max(0, min(decimal_places or 0, DECIMAL_PRECISION))
    return pa.decimal128(DECIMAL_PRECISION, scale)


def _to_timestamp(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=dt_timezone.utc)
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day, tzinfo=dt_timezone.utc)
    return value


def _to_date(value: Any) -> Optional[date]:
    if isinstance(value, datetime):
        return value.date()
    return value


def _related(value: Any) -> list:
    if value is None:
        return []
    return list(value.all()) if hasattr(value, "all") else list(value)


def _user(user: Any) -> Optional[dict]:
    if user is None:
        return None
    return {"id": user.id, "name": user.first_name}


class ParquetColumnMapper(Instance):
    """
    Describes how the values of one field type are written to a Parquet column.
    """

    def is_exported(self, field: "Field") -> bool:
        """Whether the field is written at all. Secrets are never exported."""

        return True

    def arrow_type(self, field: "Field") -> pa.DataType:
        raise NotImplementedError

    def convert(self, value: Any, field_object: "FieldObject") -> Any:
        """
        Converts the value of a row, as read from the generated model, to a Python
        value Arrow can store in the column. `None` values never reach this method.
        """

        raise NotImplementedError


class JsonColumnMapper(ParquetColumnMapper):
    """The fallback: a JSON string of the rich export value."""

    type = "__json__"

    def arrow_type(self, field: "Field") -> pa.DataType:
        return pa.string()

    def convert(self, value: Any, field_object: "FieldObject") -> Any:
        export_value = field_object["type"].get_export_value(
            value, field_object, rich_value=True
        )
        return json.dumps(export_value, default=str, ensure_ascii=False)


class TextColumnMapper(ParquetColumnMapper):
    def arrow_type(self, field: "Field") -> pa.DataType:
        return pa.string()

    def convert(self, value: Any, field_object: "FieldObject") -> Any:
        return str(value)


class NumberColumnMapper(ParquetColumnMapper):
    type = "number"

    def arrow_type(self, field: "Field") -> pa.DataType:
        return _decimal_type(field.number_decimal_places)

    def convert(self, value: Any, field_object: "FieldObject") -> Any:
        return value


class IntegerColumnMapper(ParquetColumnMapper):
    def arrow_type(self, field: "Field") -> pa.DataType:
        return pa.int64()

    def convert(self, value: Any, field_object: "FieldObject") -> Any:
        return int(value)


class BooleanColumnMapper(ParquetColumnMapper):
    type = "boolean"

    def arrow_type(self, field: "Field") -> pa.DataType:
        return pa.bool_()

    def convert(self, value: Any, field_object: "FieldObject") -> Any:
        return bool(value)


class DateColumnMapper(ParquetColumnMapper):
    type = "date"

    def arrow_type(self, field: "Field") -> pa.DataType:
        return TIMESTAMP_TYPE if field.date_include_time else pa.date32()

    def convert(self, value: Any, field_object: "FieldObject") -> Any:
        if field_object["field"].date_include_time:
            return _to_timestamp(value)
        return _to_date(value)


class TimestampColumnMapper(ParquetColumnMapper):
    def arrow_type(self, field: "Field") -> pa.DataType:
        return TIMESTAMP_TYPE

    def convert(self, value: Any, field_object: "FieldObject") -> Any:
        return _to_timestamp(value)


class DurationColumnMapper(ParquetColumnMapper):
    """Durations are whole seconds, a duration type is poorly supported by lakes."""

    type = "duration"

    def arrow_type(self, field: "Field") -> pa.DataType:
        return pa.int64()

    def convert(self, value: Any, field_object: "FieldObject") -> Any:
        if isinstance(value, timedelta):
            return int(value.total_seconds())
        return int(value)


class SingleSelectColumnMapper(ParquetColumnMapper):
    type = "single_select"

    def arrow_type(self, field: "Field") -> pa.DataType:
        return SELECT_OPTION_TYPE

    def convert(self, value: Any, field_object: "FieldObject") -> Any:
        return {"id": value.id, "value": value.value, "color": value.color}


class MultipleSelectColumnMapper(ParquetColumnMapper):
    type = "multiple_select"

    def arrow_type(self, field: "Field") -> pa.DataType:
        return pa.list_(SELECT_OPTION_TYPE)

    def convert(self, value: Any, field_object: "FieldObject") -> Any:
        return [
            {"id": option.id, "value": option.value, "color": option.color}
            for option in _related(value)
        ]


class LinkRowColumnMapper(ParquetColumnMapper):
    """Linked rows keep their id, so the lake can join, plus their primary value."""

    type = "link_row"

    def arrow_type(self, field: "Field") -> pa.DataType:
        return pa.list_(LINKED_ROW_TYPE)

    def convert(self, value: Any, field_object: "FieldObject") -> Any:
        related_rows = _related(value)
        primary_values = field_object["type"].get_export_value(
            value, field_object, rich_value=True
        )
        if not isinstance(primary_values, list) or len(primary_values) != len(
            related_rows
        ):
            primary_values = [None] * len(related_rows)

        return [
            {
                "id": related_row.id,
                "value": None if primary_value is None else str(primary_value),
            }
            for related_row, primary_value in zip(related_rows, primary_values)
        ]


class FileColumnMapper(ParquetColumnMapper):
    """
    Files are described, not linked: signed download URLs would expire long before
    the lake reads them.
    """

    type = "file"

    def arrow_type(self, field: "Field") -> pa.DataType:
        return pa.list_(FILE_TYPE)

    def convert(self, value: Any, field_object: "FieldObject") -> Any:
        return [
            {
                "name": file.get("name"),
                "visible_name": file.get("visible_name"),
                "size": file.get("size"),
                "mime_type": file.get("mime_type"),
                "is_image": file.get("is_image"),
                "uploaded_at": file.get("uploaded_at"),
            }
            for file in value or []
        ]


class MultipleCollaboratorsColumnMapper(ParquetColumnMapper):
    type = "multiple_collaborators"

    def arrow_type(self, field: "Field") -> pa.DataType:
        return pa.list_(USER_TYPE)

    def convert(self, value: Any, field_object: "FieldObject") -> Any:
        return [_user(user) for user in _related(value)]


class UserColumnMapper(ParquetColumnMapper):
    def arrow_type(self, field: "Field") -> pa.DataType:
        return USER_TYPE

    def convert(self, value: Any, field_object: "FieldObject") -> Any:
        return _user(value)


class ExcludedColumnMapper(ParquetColumnMapper):
    """Fields holding secrets, such as password hashes and edit links."""

    def is_exported(self, field: "Field") -> bool:
        return False

    def arrow_type(self, field: "Field") -> pa.DataType:
        return pa.null()

    def convert(self, value: Any, field_object: "FieldObject") -> Any:
        return None


# Formula result types that map onto a dedicated column type. Anything else, like
# arrays or select options, falls back to JSON.
FORMULA_TEXT_TYPES = {"text", "char", "url", "email", "phone_number", "link", "uuid"}


class FormulaColumnMapper(ParquetColumnMapper):
    """
    Formula, lookup, rollup and count fields are typed after their resulting formula
    type.
    """

    type = "formula"

    def _delegate(self, field: "Field") -> ParquetColumnMapper:
        formula_type = getattr(field, "formula_type", None)
        if formula_type in FORMULA_TEXT_TYPES:
            return FORMULA_TEXT_MAPPER
        if formula_type == "number":
            return NUMBER_MAPPER
        if formula_type == "boolean":
            return BOOLEAN_MAPPER
        if formula_type == "date":
            return DATE_MAPPER
        if formula_type == "duration":
            return DURATION_MAPPER
        return JSON_MAPPER

    def arrow_type(self, field: "Field") -> pa.DataType:
        return self._delegate(field).arrow_type(field)

    def convert(self, value: Any, field_object: "FieldObject") -> Any:
        return self._delegate(field_object["field"]).convert(value, field_object)


def _typed(base: type, type_name: str) -> ParquetColumnMapper:
    """Registers a shared mapper implementation under another field type name."""

    return type(f"{base.__name__}_{type_name}", (base,), {"type": type_name})()


class ParquetColumnMapperRegistry(Registry[ParquetColumnMapper]):
    name = "parquet_column_mapper"

    def get_for_field_type(self, field_type_name: str) -> ParquetColumnMapper:
        """
        Returns the mapper of a field type, or the JSON fallback when none is
        registered.
        """

        return self.registry.get(field_type_name, JSON_MAPPER)


JSON_MAPPER = JsonColumnMapper()
NUMBER_MAPPER = NumberColumnMapper()
BOOLEAN_MAPPER = BooleanColumnMapper()
DATE_MAPPER = DateColumnMapper()
DURATION_MAPPER = DurationColumnMapper()
FORMULA_TEXT_MAPPER = _typed(TextColumnMapper, "__formula_text__")

parquet_column_mapper_registry = ParquetColumnMapperRegistry()

for _mapper in [
    NUMBER_MAPPER,
    BOOLEAN_MAPPER,
    DATE_MAPPER,
    DURATION_MAPPER,
    SingleSelectColumnMapper(),
    MultipleSelectColumnMapper(),
    LinkRowColumnMapper(),
    FileColumnMapper(),
    MultipleCollaboratorsColumnMapper(),
    FormulaColumnMapper(),
    *[
        _typed(TextColumnMapper, name)
        for name in ("text", "long_text", "url", "email", "phone_number", "uuid")
    ],
    *[_typed(IntegerColumnMapper, name) for name in ("rating", "autonumber")],
    *[_typed(TimestampColumnMapper, name) for name in ("created_on", "last_modified")],
    *[_typed(UserColumnMapper, name) for name in ("created_by", "last_modified_by")],
    *[_typed(FormulaColumnMapper, name) for name in ("count", "rollup", "lookup")],
    *[
        _typed(ExcludedColumnMapper, name)
        for name in ("password", "form_view_edit_row")
    ],
]:
    parquet_column_mapper_registry.register(_mapper)
