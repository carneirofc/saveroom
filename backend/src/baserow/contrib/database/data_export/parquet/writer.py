"""
Streams the rows of a Baserow table into Parquet files on local disk.

The writer is storage agnostic: it produces part files in a directory and describes
them, the caller uploads them wherever they belong.
"""

import hashlib
import os
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional

from django.db.models import QuerySet

import pyarrow as pa
import pyarrow.parquet as pq

from .types import TIMESTAMP_TYPE, ParquetColumnMapper, parquet_column_mapper_registry

COLUMN_NAMING_FIELD_ID = "field_id"
COLUMN_NAMING_FIELD_NAME = "field_name"
COLUMN_NAMINGS = (COLUMN_NAMING_FIELD_ID, COLUMN_NAMING_FIELD_NAME)

# Columns every export has, whatever the fields of the table.
BASE_COLUMNS = [
    pa.field("id", pa.int64(), nullable=False),
    pa.field("created_on", TIMESTAMP_TYPE),
    pa.field("updated_on", TIMESTAMP_TYPE),
    pa.field("_deleted", pa.bool_(), nullable=False),
    pa.field("_run_id", pa.string(), nullable=False),
    pa.field("_extracted_at", TIMESTAMP_TYPE, nullable=False),
]
BASE_COLUMN_NAMES = {column.name for column in BASE_COLUMNS}

COMPRESSION = "zstd"
HASH_CHUNK_SIZE = 1024 * 1024


@dataclass(frozen=True)
class ParquetColumn:
    """A field of the table and how it is written."""

    name: str
    field_object: Dict[str, Any]
    mapper: ParquetColumnMapper
    arrow_type: pa.DataType

    @property
    def field(self):
        return self.field_object["field"]

    @property
    def field_type_name(self) -> str:
        return self.field_object["type"].type

    def describe(self) -> Dict[str, Any]:
        """The column as written in the export manifest."""

        return {
            "column": self.name,
            "field_id": self.field.id,
            "field_name": self.field.name,
            "field_type": self.field_type_name,
            "arrow_type": str(self.arrow_type),
            "primary": bool(getattr(self.field, "primary", False)),
        }


@dataclass(frozen=True)
class ParquetPart:
    """A part file written to local disk."""

    path: str
    file_name: str
    rows: int
    size: int
    sha256: str


def _sanitize_column_name(name: str) -> str:
    sanitized = re.sub(r"[^0-9a-zA-Z_]+", "_", name).strip("_").lower()
    return sanitized or "field"


def build_columns(
    model, column_naming: str = COLUMN_NAMING_FIELD_ID
) -> List[ParquetColumn]:
    """
    Describes the exported columns of a generated table model, in field order.

    :param model: The generated table model, from `Table.get_model()`.
    :param column_naming: `field_id` names columns `field_<id>`, stable across
        renames. `field_name` uses sanitized, unique field names instead.
    :return: The columns, without the base columns.
    """

    if column_naming not in COLUMN_NAMINGS:
        raise ValueError(f"Unknown column naming '{column_naming}'.")

    field_objects = sorted(
        model._field_objects.values(),
        key=lambda field_object: (
            not getattr(field_object["field"], "primary", False),
            field_object["field"].order,
            field_object["field"].id,
        ),
    )

    columns = []
    used_names = set(BASE_COLUMN_NAMES)
    for field_object in field_objects:
        field = field_object["field"]
        mapper = parquet_column_mapper_registry.get_for_field_type(
            field_object["type"].type
        )
        if not mapper.is_exported(field):
            continue

        if column_naming == COLUMN_NAMING_FIELD_ID:
            name = f"field_{field.id}"
        else:
            name = _sanitize_column_name(field.name)
            if name in used_names:
                name = f"{name}_{field.id}"
        used_names.add(name)

        columns.append(
            ParquetColumn(
                name=name,
                field_object=field_object,
                mapper=mapper,
                arrow_type=mapper.arrow_type(field),
            )
        )

    return columns


def build_schema(columns: List[ParquetColumn]) -> pa.Schema:
    """
    Builds the Arrow schema of an export. Each field column carries the Baserow field
    id, name and type as metadata, so the lake does not depend on the column naming.
    """

    fields = list(BASE_COLUMNS)
    for column in columns:
        fields.append(
            pa.field(
                column.name,
                column.arrow_type,
                metadata={
                    "baserow_field_id": str(column.field.id),
                    "baserow_field_name": column.field.name,
                    "baserow_field_type": column.field_type_name,
                },
            )
        )
    return pa.schema(fields)


def schema_fingerprint(columns: List[ParquetColumn], column_naming: str) -> str:
    """
    A stable hash of the exported schema. When it changes, incremental files no
    longer line up with earlier ones and a full export is needed.

    Field names only take part when they name the columns, so renaming a field does
    not force a full export with the default naming.
    """

    parts = [column_naming]
    for column in columns:
        parts.append(
            "|".join(
                [
                    column.name,
                    str(column.field.id),
                    column.field_type_name,
                    str(column.arrow_type),
                ]
            )
        )
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()


def _sha256_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(HASH_CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


class TableParquetWriter:
    """
    Writes rows to size bounded Parquet part files. Each chunk of rows becomes a row
    group, so memory use is bounded by the chunk size rather than the table size.
    """

    def __init__(
        self,
        columns: List[ParquetColumn],
        directory: str,
        run_id: str,
        extracted_at: datetime,
        chunk_size: int,
        max_rows_per_file: int,
    ):
        self.columns = columns
        self.schema = build_schema(columns)
        self.directory = directory
        self.run_id = run_id
        self.extracted_at = extracted_at
        self.chunk_size = max(1, chunk_size)
        self.max_rows_per_file = max(1, max_rows_per_file)

    def row_to_record(self, row) -> Dict[str, Any]:
        record = {
            "id": row.id,
            "created_on": getattr(row, "created_on", None),
            "updated_on": getattr(row, "updated_on", None),
            "_deleted": bool(getattr(row, "trashed", False)),
            "_run_id": self.run_id,
            "_extracted_at": self.extracted_at,
        }
        for column in self.columns:
            value = getattr(row, column.field_object["name"], None)
            record[column.name] = (
                None
                if value is None
                else column.mapper.convert(value, column.field_object)
            )
        return record

    def iter_chunks(self, queryset: QuerySet) -> Iterable[List[Any]]:
        """
        Iterates the queryset in id order with keyset pagination, which stays fast on
        large tables and plays well with the prefetches of `enhance_by_fields`.
        """

        last_id = 0
        while True:
            rows = list(
                queryset.filter(id__gt=last_id).order_by("id")[: self.chunk_size]
            )
            if not rows:
                return
            yield rows
            last_id = rows[-1].id

    def write(self, queryset: QuerySet) -> List[ParquetPart]:
        """
        Writes every row of the queryset. At least one part is always written, so an
        empty table still publishes its schema.

        :param queryset: The rows to write, including trashed rows when deletes must
            be exported.
        :return: The part files, in order.
        """

        parts: List[ParquetPart] = []
        writer: Optional[pq.ParquetWriter] = None
        path = ""
        rows_in_part = 0

        def open_part():
            nonlocal writer, path, rows_in_part
            file_name = f"part-{len(parts):05d}.parquet"
            path = os.path.join(self.directory, file_name)
            writer = pq.ParquetWriter(path, self.schema, compression=COMPRESSION)
            rows_in_part = 0
            return file_name

        def close_part(file_name):
            nonlocal writer
            writer.close()
            writer = None
            parts.append(
                ParquetPart(
                    path=path,
                    file_name=file_name,
                    rows=rows_in_part,
                    size=os.path.getsize(path),
                    sha256=_sha256_file(path),
                )
            )

        file_name = open_part()
        try:
            for rows in self.iter_chunks(queryset):
                offset = 0
                while offset < len(rows):
                    if rows_in_part >= self.max_rows_per_file:
                        close_part(file_name)
                        file_name = open_part()

                    room = self.max_rows_per_file - rows_in_part
                    batch = rows[offset : offset + room]
                    offset += len(batch)

                    table = pa.Table.from_pylist(
                        [self.row_to_record(row) for row in batch], schema=self.schema
                    )
                    writer.write_table(table)
                    rows_in_part += len(batch)

            close_part(file_name)
        except Exception:
            if writer is not None:
                writer.close()
            raise

        return parts
