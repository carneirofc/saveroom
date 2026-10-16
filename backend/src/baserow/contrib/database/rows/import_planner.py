"""
Computes what a file import into an existing table would change. The import preview
and the import itself both use `ImportPlanner`, so what is previewed is exactly what
gets written.
"""

import dataclasses
from typing import Any, Optional, Type

from django.contrib.auth.models import AbstractUser
from django.db.models.fields.related import ManyToManyField

from baserow.contrib.database.fields.exceptions import FieldNotInTable
from baserow.contrib.database.table.models import GeneratedTableModel, Table
from baserow.core.utils import Progress, grouper

from .constants import (
    IMPORT_MATCHING_MODES,
    IMPORT_MODE_INSERT,
    IMPORT_MODE_REPLACE,
    IMPORT_MODE_UPDATE,
    IMPORT_MODE_UPSERT,
)
from .error_report import RowErrorReport
from .exceptions import ImportAmbiguousMatches
from .handler import RowHandler, UpsertRowsMappingHandler
from .types import FileImportConfiguration

COMPARE_CHUNK_SIZE = 1000


@dataclasses.dataclass
class PlannedUpdate:
    import_index: int
    row_id: int
    # The values to write: only the changed fields plus the `id`.
    values: dict[str, Any]
    changed_field_ids: list[int]
    # The internal values of the changed fields before the import plus the `id`,
    # used to undo the import.
    original_values: dict[str, Any]


@dataclasses.dataclass
class ImportPlan:
    mode: str
    error_report: RowErrorReport
    # (import index, row values) of the rows to create.
    to_create: list[tuple[int, dict[str, Any]]] = dataclasses.field(
        default_factory=list
    )
    to_update: list[PlannedUpdate] = dataclasses.field(default_factory=list)
    # (import index, row id) of the matched rows that wouldn't change.
    unchanged: list[tuple[int, int]] = dataclasses.field(default_factory=list)
    # Import indexes of the unmatched rows ignored by the `update` mode.
    skipped: list[int] = dataclasses.field(default_factory=list)
    to_delete_ids: list[int] = dataclasses.field(default_factory=list)
    ambiguous: list[dict[str, Any]] = dataclasses.field(default_factory=list)
    ambiguous_blocked: bool = False

    def summary(self) -> dict[str, int]:
        return {
            "create": len(self.to_create),
            "update": len(self.to_update),
            "unchanged": len(self.unchanged),
            "delete": len(self.to_delete_ids),
            "skipped": len(self.skipped),
            "errors": len(self.error_report.to_dict()),
        }


class ImportPlanner:
    """
    Plans a file import without writing anything: validates and reshapes the imported
    rows, matches them with the existing rows and splits them into rows to create,
    update, leave unchanged, skip and delete.
    """

    def __init__(
        self,
        user: AbstractUser,
        table: Table,
        data: list[list[Any]],
        configuration: Optional[FileImportConfiguration] = None,
        model: Optional[Type[GeneratedTableModel]] = None,
        validate: bool = True,
        progress: Optional[Progress] = None,
        raise_on_ambiguity: bool = True,
    ):
        """
        :param user: The user on whose behalf the import runs.
        :param table: The table the rows are imported into.
        :param data: The imported rows, one value per writable field.
        :param configuration: The import configuration.
        :param model: The table model, if already generated.
        :param validate: Validate the rows with the row serializer.
        :param progress: Progress to increment during the validation.
        :param raise_on_ambiguity: Raise `ImportAmbiguousMatches` when the match keys
            are ambiguous and not explicitly allowed. The preview disables it to
            report them instead.
        """

        self.user = user
        self.table = table
        self.data = data
        self.configuration = configuration or {}
        self.model = model or table.get_model()
        self.validate = validate
        self.progress = progress
        self.raise_on_ambiguity = raise_on_ambiguity

    @property
    def mode(self) -> str:
        return self.configuration.get("mode") or (
            IMPORT_MODE_UPSERT
            if self.configuration.get("upsert_fields")
            else IMPORT_MODE_INSERT
        )

    def plan(self) -> ImportPlan:
        """
        :raises InvalidRowLength: When the upsert values don't match the upsert fields.
        :raises FieldNotInTable: When a skipped or upsert field isn't in the table.
        :raises ImportAmbiguousMatches: When the match keys are ambiguous.
        :return: The import plan.
        """

        mode = self.mode
        matching = mode in IMPORT_MATCHING_MODES
        mapping_handler = UpsertRowsMappingHandler(
            table=self.table,
            upsert_fields=(self.configuration.get("upsert_fields") or [])
            if matching
            else [],
            upsert_values=(self.configuration.get("upsert_values") or [])
            if matching
            else [],
        )
        mapping_handler.validate()

        error_report = RowErrorReport(self.data)
        plan = ImportPlan(mode=mode, error_report=error_report)
        skipped_field_names = self._get_skipped_field_names()
        valid_rows, index_mapping = self._get_valid_rows(error_report)

        try:
            update_map = mapping_handler.process_map
            plan.ambiguous = mapping_handler.ambiguous_keys()
        finally:
            mapping_handler.cleanup()

        # Imports without an explicit mode predate the ambiguity check and keep
        # pairing duplicates in order.
        allow_ambiguous = self.configuration.get(
            "allow_ambiguous_matches"
        ) or not self.configuration.get("mode")
        if plan.ambiguous and not allow_ambiguous:
            plan.ambiguous_blocked = True
            if self.raise_on_ambiguity:
                raise ImportAmbiguousMatches(plan.ambiguous)

        candidates = []
        for current_idx, import_idx in index_mapping.items():
            row = valid_rows[current_idx]
            row_id = update_map.get(import_idx)
            if row_id:
                # Skipped fields are not overwritten, existing values are preserved.
                values = {k: v for k, v in row.items() if k not in skipped_field_names}
                candidates.append((import_idx, row_id, values))
            elif mode == IMPORT_MODE_UPDATE:
                plan.skipped.append(import_idx)
            else:
                plan.to_create.append((import_idx, row))

        self._plan_updates(candidates, plan)

        if mode == IMPORT_MODE_REPLACE:
            plan.to_delete_ids = self._get_existing_row_ids()
        elif matching and self.configuration.get("delete_unmatched"):
            # Rows matched by an imported row are never deleted, even if that row
            # failed validation.
            matched_ids = set(update_map.values())
            plan.to_delete_ids = [
                row_id
                for row_id in self._get_existing_row_ids()
                if row_id not in matched_ids
            ]

        return plan

    def _get_skipped_field_names(self) -> set[str]:
        skipped_field_ids = self.configuration.get("skipped_fields") or []
        try:
            return {
                self.model.get_field_object_by_id(field_id)["name"]
                for field_id in skipped_field_ids
            }
        except ValueError:
            raise FieldNotInTable("The field ID is not found in the table.")

    def _get_valid_rows(
        self, error_report: RowErrorReport
    ) -> tuple[list[dict[str, Any]], dict[int, int]]:
        """
        Reshapes the imported rows by field, validates them and removes the values
        of the fields the user can't write.

        :return: The valid rows and the mapping valid row index -> import index.
        """

        fields = [
            field_object["field"]
            for field_object in self.model._field_objects.values()
            if not field_object["type"].read_only
            and not field_object["field"].read_only
        ]

        # Sort by primary first (descending), then by order, then by id
        fields.sort(key=lambda f: (not f.primary, f.order, f.id))

        for index, row in enumerate(self.data):
            if len(row) > len(fields):
                error_report.add_error(
                    index,
                    {"non_field_errors": ["Too many values in this line."]},
                )
            else:
                new_row = list(row)
                # Fill incomplete rows with empty values
                new_row.extend([None] * (len(fields) - len(row)))

                # Reshape data by field as expected by the import
                error_report.update_row(
                    index,
                    {
                        f"field_{fields[index].id}": value
                        for index, value in enumerate(new_row)
                    },
                )

        handler = RowHandler()
        if self.validate:
            valid_rows, index_mapping = error_report.get_valid_rows_and_mapping()
            validation_sub_progress = (
                self.progress.create_child(50, len(valid_rows))
                if self.progress
                else None
            )
            validation_report = handler.validate_rows(
                self.table, valid_rows, progress=validation_sub_progress
            )
            for index, error in validation_report.items():
                error_report.add_error(index_mapping[int(index)], error)

        valid_rows, index_mapping = error_report.get_valid_rows_and_mapping()

        # Make sure to exclude fields that cannot be written by the user.
        # NOTE: all rows contain the same fields, so we can just check the first one
        unwritable_fields = handler._check_write_fields_values_permissions(
            self.user, self.model, valid_rows[:1], raise_if_not_permitted=False
        )
        unwritable_field_names = {f.db_column for f in unwritable_fields}
        valid_rows = [
            {k: v for k, v in row.items() if k not in unwritable_field_names}
            for row in valid_rows
        ]
        return valid_rows, index_mapping

    def _plan_updates(
        self, candidates: list[tuple[int, int, dict[str, Any]]], plan: ImportPlan
    ):
        """
        Compares the matched rows with their imported values and only keeps the
        changed fields. Rows without any change are marked as unchanged.
        """

        if not candidates:
            return

        model = self.model
        handler = RowHandler()
        field_objects = model._field_objects
        field_object_by_name = {o["name"]: o for o in field_objects.values()}
        m2m_field_names = [
            name
            for name in field_object_by_name
            if isinstance(model._meta.get_field(name), ManyToManyField)
        ]

        for chunk in grouper(COMPARE_CHUNK_SIZE, candidates):
            prepared_rows, failing_rows = handler.prepare_rows_in_bulk(
                field_objects,
                [values for _, _, values in chunk],
                generate_error_report=True,
            )
            for chunk_index, errors in failing_rows.items():
                plan.error_report.add_error(
                    chunk[chunk_index][0],
                    {name: [str(e) for e in errs] for name, errs in errors.items()},
                )

            failing_indexes = set(failing_rows.keys())
            valid_chunk = [
                item for index, item in enumerate(chunk) if index not in failing_indexes
            ]
            rows_by_id = {
                row.id: row
                for row in model.objects.filter(
                    id__in=[row_id for _, row_id, _ in valid_chunk]
                ).prefetch_related(*m2m_field_names)
            }

            for (import_idx, row_id, values), prepared in zip(
                valid_chunk, prepared_rows
            ):
                row = rows_by_id.get(row_id)
                if row is None:
                    # The row has been deleted in the meantime.
                    continue

                changed_values = {"id": row_id}
                original_values = {"id": row_id}
                changed_field_ids = []
                for name, prepared_value in prepared.items():
                    field_object = field_object_by_name.get(name)
                    if field_object is None:
                        continue
                    field_type = field_object["type"]
                    existing_value = field_type.get_internal_value_from_db(row, name)
                    if not field_type.are_import_values_equal(
                        existing_value, prepared_value
                    ):
                        changed_values[name] = values[name]
                        original_values[name] = existing_value
                        changed_field_ids.append(field_object["field"].id)

                if changed_field_ids:
                    plan.to_update.append(
                        PlannedUpdate(
                            import_index=import_idx,
                            row_id=row_id,
                            values=changed_values,
                            changed_field_ids=changed_field_ids,
                            original_values=original_values,
                        )
                    )
                else:
                    plan.unchanged.append((import_idx, row_id))

    def _get_existing_row_ids(self) -> list[int]:
        return list(self.model.objects.order_by("id").values_list("id", flat=True))
