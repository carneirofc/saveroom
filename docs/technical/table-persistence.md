# Table persistence

Saveroom does not store user data in a generic key/value or entity-attribute-value layout.
Every table a user creates becomes a **real PostgreSQL table**, created at runtime with real
columns and real indexes. This document explains what exists in the database for a given
Saveroom table, how it is named, which code path creates, alters and drops it, and what
happens when a user deletes something.

This is a deeper companion to the [database plugin](./database-plugin.md) overview.

## Two layers of storage

There are two distinct layers, and it is important not to confuse them.

**The metadata layer** consists of ordinary Django models with ordinary Django migrations:
`Database` (an application), `Table`, `Field` (and its per-type subclasses), `View`, and so
on. These live in fixed tables such as `database_table` and `database_field`, and they
describe *what* the user has built.

**The data layer** consists of one physical PostgreSQL table per Saveroom table, plus a
through table per many-to-many relationship. These tables are created, altered and dropped
directly by application code — they have no migration files and Django's migration state
knows nothing about them.

So a Saveroom table with id `42` is described by a row in `database_table` *and* backed by a
physical table called `database_table_42`.

## Naming

All prefixes are defined in
`backend/src/baserow/contrib/database/table/constants.py`. Nothing else should hardcode them.

| Object | Physical name | Derived by |
|---|---|---|
| User table | `database_table_<table_id>` | `Table.get_database_table_name()` |
| Field value column | `field_<field_id>` | `Field.db_column` |
| `(order, id)` index | `tbl_order_id_<table_id>_idx` | `Table.get_collision_safe_order_id_idx_name()` |
| Link row through table | `database_relation_<link_row_relation_id>` | `LinkRowField.through_table_name` |
| Multiple select through table | `database_multipleselect_<field_id>` | `MultipleSelectField.through_table_name` |
| Multiple collaborators through table | `database_multiplecollaborators_<field_id>` | `MultipleCollaboratorsField.through_table_name` |
| Workspace search table | `database_search_workspace_<workspace_id>_data` | `SearchHandler.get_workspace_search_table_name()` |
| Legacy per-field search column | `tsv_field_<field_id>` | `get_tsv_vector_field_name()` |

Two details are easy to get wrong:

* Link row through tables are keyed by `link_row_relation_id` — a `SerialField` on
  `LinkRowField` — **not** by the field id. Both sides of a bidirectional link share a single
  relation id, and therefore a single through table. Multiple select and multiple
  collaborators through tables are keyed by the field's own id.
* The `(order, id)` index name is generated explicitly rather than by Django. Django's
  automatic index naming truncates and hashes, and at Saveroom's scale that produced name
  collisions often enough to matter (roughly five per thousand tables), so
  `get_collision_safe_order_id_idx_name()` builds a name from the table id instead.

## The generated model

Because the data layer has no static Django models, Saveroom builds one on demand.
`Table.get_model()` in `backend/src/baserow/contrib/database/table/models.py` constructs a
Django model class at runtime and returns it. This is the single entry point for reading or
writing user data.

```python
from baserow.contrib.database.table.models import Table

table = Table.objects.get(pk=42)
model = table.get_model()

for row in model.objects.all():
    print(row.id, row.field_1234)
```

The class it produces is named `Table<id>Model` and has a `Meta` containing:

* `db_table` — the physical name from `get_database_table_name()`.
* `managed` — `False` by default. Django must not try to manage a table it has no migrations
  for; `managed=True` is passed only in the moment the schema editor needs to create or drop
  the physical table.
* `ordering = ["order", "id"]`, and a matching index on `(order, id)`.
* `app_label` — a fresh `uuid4()` per call. Related fields register pending operations in the
  Django app registry keyed by model class name, so two threads generating the same table's
  model concurrently could otherwise resolve those operations in the wrong order. A unique
  app label isolates each generation.

The bases are `GeneratedTableModel`, `TrashableModelMixin`, `CreatedAndUpdatedOnMixin` and
`models.Model`. `GeneratedTableModel` is also how the rest of the codebase recognises these
classes — `isinstance(obj, GeneratedTableModel)` is a valid check.

`get_model()` accepts several arguments worth knowing:

* `attribute_names=True` names attributes after the user's field names instead of
  `field_<id>`, deduplicating collisions by appending `_field_<id>`.
* `field_ids` / `field_names` restrict the model to a subset of columns, which matters for
  wide tables.
* `fields` supplies already-fetched `Field` instances so the model can be built without
  re-querying.

The class also carries `_field_objects` and `_trashed_field_objects`: dicts keyed by field id
holding the `FieldType`, the `Field` instance, and the attribute name used on the model.
Nearly all field-aware code walks these rather than Django's `_meta`.

Two managers are attached. `objects` (a `TableModelManager`) filters `trashed=False`;
`objects_and_trash` does not. Both return a `TableModelQuerySet`, which is where search,
filtering, sorting and `enhance_by_fields()` prefetching are implemented.

### Model caching

Building a model means querying every field of the table, so the result is cached in two
layers (`backend/src/baserow/contrib/database/table/cache.py`).

A process-local cache keyed `database_table_model_<table_id>` avoids rebuilding the same
model twice within a single request. Behind it, the field attributes are cached in a
Redis-backed Django cache under `full_table_model_<table_id>_<BASEROW_VERSION>` — namespaced
by release so an upgrade invalidates everything automatically.

Invalidation is version-based rather than key-based. Each `Table` row has a `version` column;
a cache entry is only used if its stored version matches. `invalidate_table_in_model_cache()`
sets `version` to a fresh `uuid4()`, clears the local cache and sends the
`table_schema_changed` signal, which makes every existing cache entry for that table stale
without having to delete it.

> `BASEROW_DISABLE_MODEL_CACHE` turns the shared cache off entirely, which is occasionally
> useful when debugging schema issues.

## Columns present on every row

Beyond the user's own `field_<id>` columns, every user table carries system columns.

| Column | Type | Where it comes from |
|---|---|---|
| `id` | `AutoField` primary key (per `DEFAULT_AUTO_FIELD`) | implicit Django PK |
| `order` | `DecimalField(max_digits=40, decimal_places=20)` | added in `get_model()` |
| `created_on` / `updated_on` | `DateTimeField(auto_now_add=True)` / `SyncedDateTimeField(auto_now=True)` | `CreatedAndUpdatedOnMixin` |
| `trashed` | `BooleanField(default=False, db_index=True)` | `TrashableModelMixin` |
| `created_by` / `last_modified_by` | nullable FK to the user table | added conditionally |
| `needs_background_update` | `BooleanField(default=False)` | added conditionally, deprecated |
| field rules state | see `FieldRuleHandler.get_state_column()` | added conditionally |

`created_by` and `last_modified_by` use `IgnoreMissingForeignKey` with `db_constraint=False`
and `on_delete=DO_NOTHING`. There is deliberately no foreign key constraint to the user
table: adding one to every user table would make user deletion prohibitively expensive.

### Why some columns are conditional

`Table` carries a set of boolean backfill flags — `needs_background_update_column_added`,
`last_modified_by_column_added`, `created_by_column_added`,
`field_rules_validity_column_added`, `missing_m2m_indexes_added`. `get_model()` only adds the
corresponding column to the generated model when the flag is set.

This is the central consequence of the whole design. When Saveroom introduces a new system
column, it cannot ship a migration for it: there are N physical tables, one per user table,
and the number grows without bound. Instead the column is added to each table lazily at
runtime — see `TableHandler.create_created_by_and_last_modified_by_fields()` — and the flag on
the `Table` row (which *is* migrated) records whether that backfill has already run for that
particular table. Periodic tasks in `table/tasks.py` work through the backlog.

## Schema changes

All DDL goes through helpers in `backend/src/baserow/contrib/database/db/schema.py`. Code in
this area should not call `connection.schema_editor()` directly.

`safe_django_schema_editor()` yields a `SafeBaserowPostgresSchemaEditor`. It exists for two
reasons. First, self-referencing link row fields produce a through table that both sides of
the relationship believe they own, so a naive `create_model` / `delete_model` tries to create
or drop the same table twice; the safe editor tracks what it has already done. Second, it
works around a Django bug where the surrounding atomic block is not exited correctly if
deferred SQL fails. It also adds `create_model_tracking_created_m2ms()`,
`ensure_single_column_index()` and `ensure_m2m_field_indexes()`.

`lenient_schema_editor()` layers `PostgresqlLenientDatabaseSchemaEditor` on top. A plain
`ALTER TABLE ... ALTER COLUMN ... TYPE` fails outright if a single value cannot be cast. That
is unacceptable here: a user changing a text field to a number field expects the
non-numeric cells to empty out, not the request to fail. The lenient editor installs a
temporary PostgreSQL try-cast function for the duration of the statement so uncastable values
become `NULL` instead.

### Creating a table

`TableHandler.create_table()` delegates to `create_table_and_fields()`, which creates the
`Table` row, creates each `Field` row directly, creates the default grid view, and then issues
a **single** DDL statement for the whole table:

```python
with safe_django_schema_editor() as schema_editor:
    model = table.get_model(managed=True)
    schema_editor.create_model(model)
```

One `CREATE TABLE` covers every field, rather than a create followed by N alters. The same
`create_model` call also creates any auto-generated many-to-many through tables. Database
import and duplication take an equivalent path in `application_types.py`, using
`create_model_tracking_created_m2ms()` so through tables shared across several tables in one
import batch are not created twice.

### Adding and changing fields

`FieldHandler.create_field()` creates the `Field` row, then generates a model containing only
that field and calls `schema_editor.add_field()`, followed by `add_constraint()` for any
field constraints.

`FieldHandler.update_field()` first asks `field_converter_registry.find_applicable_converter()`
whether a registered converter handles this particular type transition. If one matches, it
owns the entire operation. Otherwise the default path runs: the old field type supplies
`get_alter_column_prepare_old_value()`, the new one supplies
`get_alter_column_prepare_new_value()`, and those SQL expressions are handed to the lenient
schema editor, which then performs `alter_field()`.

`force_same_type_alter_column()` forces that conversion SQL to run even when the underlying
PostgreSQL column type is unchanged — necessary when the *meaning* of the stored value
changes, for example between two select-option-backed field types.

Converters live in `fields/field_converters.py`. `RecreateFieldConverter` simply drops and
re-adds the column, discarding the data; it backs the formula, link row, file,
multiple collaborators, autonumber and password field types, whose storage is too different
from anything else to convert in place. Purpose-built converters handle the transitions where
data *can* be preserved, notably text ↔ multiple select and single select ↔ multiple select.

> Converters are pluggable. See the
> [field converter plugin page](../plugins/field-converter.md).

### Through tables

Link row, multiple select and multiple collaborators fields have no column of their own on
the user table. Instead the field type attaches a `ManyToManyField` to the generated model
with `db_table` set to the field's `through_table_name` and `db_constraint=False` — for link
rows this happens in `LinkRowFieldType.after_model_generation()`, which must run after both
tables' models exist.

When such a field is added to a table that already exists, `schema_editor.add_field()` creates
the through table but *not* the indexes on its foreign key columns. `ensure_m2m_field_indexes()`
adds them, and `Table.missing_m2m_indexes_added` tracks which tables have been fixed up.

## Row ordering

`order` is a high-precision decimal, not a sequence. Inserting a row between two existing rows
computes a fraction between their orders, so no other row has to be touched.

`RowHandler.get_unique_orders_before_row()` implements this. With a `before` row it calls
`get_unique_orders_before_item()`, which finds the largest order strictly below the target and
bisects towards it with `find_intermediate_order()`, rounding to twenty decimal places. With
no `before` row it takes `ceil(max(order))` and steps up in whole numbers.

Twenty decimal places is finite, so repeated insertion at the same point eventually exhausts
the available fractions and raises `CannotCalculateIntermediateOrder`. The handler catches it,
calls `recalculate_row_orders()`, which renumbers every row to consecutive whole numbers while
preserving relative order, and then retries. This is the one ordering operation that rewrites
the whole table.

## Search data

Row search is stored, not computed at query time, and there are currently two generations of
it. `SearchHandler` in `backend/src/baserow/contrib/database/search/` is aware of both.

The **legacy** scheme keeps one `tsvector` column named `tsv_field_<field_id>` per searchable
field, on the user table itself. Deployments that predate the change may still have these.
The `drop_tsv_columns` management command removes leftovers once a table has migrated.

The **current** scheme keeps one search table per workspace, named
`database_search_workspace_<workspace_id>_data`. Its model is generated dynamically by
`_generate_search_table_model()` in much the same way as a user table model, from the
`AbstractSearchValue` base: `row_id`, `field_id`, `updated_on`, and a `SearchVectorField`
called `value`, with `unique_together = ("field_id", "row_id")` and a GIN index on `value`.
Creation and deletion use `SearchDatabaseSchemaEditor`, whose `sql_delete_table` is
`DROP TABLE IF EXISTS %(table)s CASCADE`.

Which path a query takes is decided by `SearchHandler.can_use_full_text_search()` and the
search mode (`SearchMode.COMPAT` versus `SearchMode.FT_WITH_COUNT`), consumed by
`TableModelQuerySet.search_all_fields()`.

Search data is never updated synchronously with the write that caused it. Changes queue
`PendingSearchValueUpdate` rows which Celery tasks in `search/tasks.py` drain in batches. The
deprecated `needs_background_update` column was the original, coarser marker for the same job
before the pending-update table replaced it.

> Do not confuse this with [workspace search](./workspace-search.md), which is the separate
> feature for finding tables, views and rows across a whole workspace.

## Trash and deletion

Deleting things in Saveroom almost never issues DDL immediately.

Trashing a **table** sets `trashed=True` on the `Table` row and cascades `trashed=True` onto
its fields. The physical `database_table_<id>` table is untouched and still holds every row —
which is exactly what makes restore cheap and complete.

Trashing a **row** sets that row's `trashed` column. The default manager filters it out; the
`objects_and_trash` manager still sees it.

Trashing a **field** marks the `Field` row. The column survives, and the generated model keeps
it in `_trashed_field_objects` (prefixing the attribute name with `trashed_` if it would
collide). This matters: if the model omitted the column entirely, inserting a new row would
leave it `NULL` and violate a `NOT NULL` constraint on a column the model does not know about.

Real DDL only happens when the trash retention period expires and
`baserow/core/trash/` calls the permanent-delete hooks in
`backend/src/baserow/contrib/database/trash/trash_types.py`:

* `TableTrashableItemType.permanently_delete_item()` calls `schema_editor.delete_model()` —
  a real `DROP TABLE`, cascading to the through tables — and then deletes the `Table` row.
* `FieldTrashableItemType.permanently_delete_item()` calls `schema_editor.remove_field()` —
  a real `ALTER TABLE ... DROP COLUMN` — and then deletes the `Field` row.

Both first evict the table from the model lookup cache they are passed, since any model still
referring to the dropped column or table would raise `ProgrammingError` on next use.

`FieldHandler.delete_field()` takes a `DeleteFieldStrategyEnum` for callers that need
something other than the default: `TRASH` (no DDL), `PERMANENTLY_DELETE` (drop the column
now), or `DELETE_OBJECT` (remove the metadata row only, leaving the column in place).

## Consequences for operators

The table-per-table design has direct operational implications.

The number of physical tables grows with user activity and is effectively unbounded. A busy
instance can hold hundreds of thousands of tables. This is why a whole-database `pg_dump` is
not a workable backup strategy: `pg_dump` takes an `ACCESS SHARE` lock on every table in one
transaction, which requires raising `max_locks_per_transaction` past the table count and
sizing shared memory to match, while blocking users from altering or deleting tables for the
duration. See [the backups ADR](../adr/002-baserow-data-backups.md) for the full analysis and
the chosen approach.

New system columns roll out lazily rather than through migrations, so immediately after an
upgrade some tables will have a column and others will not. The `*_column_added` flags on
`Table` are the source of truth for which is which.

Finally, `migrate` says nothing about the health of the data layer. Schema drift there is
repaired by handlers and background tasks, not by the migration framework.
