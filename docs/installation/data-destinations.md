# Data destinations, backups and datalake exports

Saveroom can write two kinds of data to storage outside the instance:

* **Backups** — the regular workspace export archive (structure and rows, signed and
  checksummed), uploaded to external storage and restorable onto this or a fresh
  instance.
* **Datalake exports** — the rows of database tables as Parquet files, on a schedule,
  full the first time and incremental afterwards, for a datalake to ingest.

Both write to a **data destination**: an S3 or S3-compatible bucket, an Azure Blob
Storage container, or a mounted filesystem.

In the app, backups live under the workspace menu → **Backups** (back up now, restore,
schedules and external storage), and datalake exports under a database's menu →
**Datalake exports**. Everything below is also available through the API and management
commands.

## Declaring destinations

Destinations are declared by the operator with the `BASEROW_DATA_DESTINATIONS`
environment variable, a JSON list. Credentials live only there — never in the database
or in API responses. Schedules and API calls refer to a destination by its `name`.

Every destination has:

| Key | Required | Description |
| --- | --- | --- |
| `name` | yes | A url-safe slug schedules refer to. |
| `type` | yes | `s3`, `azure` or `filesystem`. |
| `prefix` | no | Key prefix everything is written under. |
| `purposes` | no | Subset of `["backup", "datalake"]`, both by default. A destination can only be used for the purposes it lists. |
| `allow_trust_public_key` | no | Allow a staff member to trust the signing key of a backup made by another instance when restoring from here. `false` by default. |

Any secret can be given as `<key>_file` instead of inline: the file is read at startup,
which works with Docker and Kubernetes secret mounts. Unknown keys, a half key pair or an
unreadable secret file stop the instance at startup with an explanatory error.

### S3 and S3-compatible storage

Requires `bucket`. Optional: `region`, `endpoint_url` (MinIO, Ceph RGW, …),
`addressing_style`, `signature_version`, `use_ssl`, `verify`, `access_key_id`,
`secret_access_key`, `session_token`. Without static keys, the standard AWS credential
chain is used (IRSA, Pod Identity, instance profile).

To have every object encrypted at rest by S3, set `server_side_encryption` to `AES256`
(SSE-S3) or `aws:kms` (SSE-KMS); with `aws:kms`, `sse_kms_key_id` optionally names the
key (omit it for the bucket's default KMS key). `sse_kms_key_id` is refused without
`aws:kms`.

```json
[
  {
    "name": "lake",
    "type": "s3",
    "bucket": "baserow-lake",
    "endpoint_url": "http://minio:9000",
    "addressing_style": "path",
    "purposes": ["datalake"],
    "access_key_id_file": "/run/secrets/minio/access-key-id",
    "secret_access_key_file": "/run/secrets/minio/secret-access-key"
  }
]
```

### Azure Blob Storage

Requires `container` and one of `account_key`, `connection_string` or `sas_token`, plus
`account_name` unless a connection string is given. Optional: `endpoint_suffix`,
`custom_domain`. Blob encryption is not configurable per destination: the storage
account's (or container's) default encryption, including an encryption scope set as the
container default, applies.

```json
[
  {
    "name": "offsite",
    "type": "azure",
    "container": "baserow-backups",
    "account_name": "examplestorage",
    "account_key_file": "/run/secrets/azure/account-key",
    "purposes": ["backup"]
  }
]
```

### Filesystem

Requires an absolute `root`, typically a mounted volume or PVC that is available to the
backend and Celery worker containers.

```json
[{"name": "nas", "type": "filesystem", "root": "/mnt/baserow-exports"}]
```

`GET /api/data-destinations/` lists the configured names, types and purposes.

For Docker Compose, set the variable in `.env`; the root `docker-compose.yaml` forwards
it. For Helm, see [Install with Helm](install-with-helm.md#data-destinations).

## Backups to a destination

Pass a `destination` when starting a backup or creating a backup schedule:

```sh
curl -X POST "$BASEROW/api/backups/workspace/1/async/" \
  -H "Authorization: JWT $TOKEN" -H "Content-Type: application/json" \
  -d '{"destination": "offsite"}'
```

The archive is made as usual, then uploaded to
`backups/workspace=<id>/<timestamp>_<uuid>.zip` with a `.zip.json` sidecar describing it
(workspace, applications, checksum, signing key, schedule). The sidecar is written last:
an archive without one is an incomplete upload and is ignored. A schedule's `keep_last`
and `keep_days` apply to the backups it uploaded too.

If the sidecar cannot be written, the archive is deleted again. Retention also sweeps
archives that have no sidecar and are more than 24 hours old, the leftovers of uploads
that died halfway. The sweep cannot tell which instance made such an archive, so the
age threshold is what protects an upload still in progress on a shared destination.

Retention runs when a schedule is due (the tick is
`BASEROW_BACKUP_SCHEDULE_TICK_CRONTAB`, every minute by default), usually before the
new backup has been uploaded, so `keep_last` of N briefly leaves N+1 backups. Changing a schedule's
destination leaves the backups on the old destination outside its retention. Sidecars
contain the workspace name and the email of the user who made the backup.

Listing and restoring work from the destination alone, so they also work on a fresh
instance whose database is gone:

```sh
# The API
GET  /api/backups/destinations/<name>/workspace/<workspace_id>/
POST /api/backups/destinations/<name>/workspace/<workspace_id>/restore/
     {"key": "backups/workspace=1/20260101T030000Z_<uuid>.zip"}

# Or the management commands
./baserow list_destination_backups --destination offsite --workspace-id 1
./baserow restore_from_destination --destination offsite --workspace-id 7 \
    --user-email admin@example.com --key backups/workspace=1/20260101T030000Z_<uuid>.zip
./baserow backup_to_destination 1 --destination offsite --user-email admin@example.com
```

Restored applications are installed as new applications. The archive's checksum is
verified against the sidecar first. The download and verification happen before the
import job is created, and a restore is refused up front when the user already has the
maximum number of import jobs running; if the job cannot be started, the downloaded
copy is removed again. Sidecars that are not JSON objects are skipped when listing.

Restoring needs export access to the workspace the backup was made of, the same access
listing needs. A backup made by another instance (a different `instance_id` in its
sidecar), such as on a fresh instance after a disaster, can only be restored by staff:
use the admin API or `restore_from_destination` with a staff `--user-email`.

Who sees which remote backup: staff see everything on the destination. Anyone else only
sees backups made by this instance (matching `instance_id`). A workspace admin sees all
of those for the workspace; a regular member only sees, and can only restore, the
backups they made themselves (matched on the sidecar's `created_by_id`, or on
`created_by` for older sidecars).

Backup schedules (and manual runs of table export schedules) can only be changed,
deleted or run by their owner, a workspace admin or staff, because they run with the
owner's permissions. A schedule whose owner is deactivated or pending deletion is
disabled by the periodic task. API client keys only work in the workspace they were
created in.

Several instances may share a destination. Retention only deletes the backups the
instance itself uploaded, even when another instance has a workspace or schedule with
the same id.

A schedule's retention only ever considers the backups that schedule made: manual
backups and the backups of other schedules are never removed by it. Schedules are
evaluated in their own timezone; a time repeated when the clocks go back runs once,
and a time skipped when they go forward runs right after the jump. When a schedule is
due while its user still has a backup running, it is retried five minutes later
rather than skipped until its next cron match, and `last_run_on` only moves when a
backup actually started.

Archives are signed with a key of the instance that made them. Restoring one made by
another instance fails with `ERROR_UNTRUSTED_PUBLIC_KEY` until its key is trusted: a staff
member can pass `"trust_public_key": true` (or `--trust-public-key`) when the destination
sets `allow_trust_public_key`, and only if the key inside the archive matches the one in
the sidecar.

## Datalake exports

A table export schedule exports some or all tables of a database to a destination
declared for the `datalake` purpose:

```sh
curl -X POST "$BASEROW/api/database/data-export/schedules/workspace/1/" \
  -H "Authorization: JWT $TOKEN" -H "Content-Type: application/json" \
  -d '{"database_id": 12, "name": "Hourly to lake", "cron": "0 * * * *",
       "destination": "lake", "table_ids": [34, 35]}'
```

| Endpoint | Purpose |
| --- | --- |
| `GET/POST schedules/workspace/<workspace_id>/` | List or create schedules. |
| `GET/PATCH/DELETE schedules/<id>/` | Read, change or delete a schedule. |
| `POST schedules/<id>/run/` | Export now, `{"mode": "auto" \| "full" \| "incremental"}`. |
| `GET schedules/<id>/runs/` | The last runs, one per table. |
| `POST schedules/<id>/reset-state/` | Forget watermarks; the next export of every table is full. |

Exports run with the permissions of the user who created or last updated the schedule,
re-checked on every run. To drive exports from an external scheduler instead, create
an inactive schedule and run it with:

```sh
./baserow export_table_parquet --schedule-id 3 [--table-id 34] [--mode full]
```

### Layout

Every run of a table is published as:

```
tables/workspace=<id>/database=<id>/table=<id>/schedule=<id>/
  mode=full|incremental/run=<YYYYMMDDTHHMMSSZ>_<run id>/
    part-00000.parquet
    part-00001.parquet
    _manifest.json
    _SUCCESS
  _state/latest.json
```

**Ignore a run without `_SUCCESS`.** The manifest lists the files with their row counts
and checksums, the columns with their Saveroom field id, name and type, the snapshot
moment and the reason a run was full.

Columns: `id`, `created_on`, `updated_on`, `_deleted`, `_run_id`, `_extracted_at`, then
one column per field, named `field_<id>` so renaming a field never breaks the lake
schema (`column_naming: "field_name"` uses sanitized names instead). Values are typed:
decimals, dates and timestamps, booleans, structs for select options and users, lists
for links, multiple selects and files. Formula, lookup and rollup fields follow their
result type. Password fields and form edit links are never exported.

### Merging into the lake

* A **full** run (`"semantics": "replace"`) holds every row, including trashed rows with
  `_deleted = true`, and replaces the table.
* An **incremental** run (`"semantics": "upsert"`) holds the rows whose `updated_on`
  changed since the previous run, trashed ones included. Merge by `id`, keep the row
  with the highest `updated_on`, then drop rows where `_deleted` is true.

An incremental run deliberately reaches back
`BASEROW_DATA_EXPORT_WATERMARK_OVERLAP_SECONDS` (300 by default) before the previous
snapshot, to catch rows committed late, so the same row version can arrive twice — the
merge above makes that harmless.

A run is full instead of incremental when the table was never exported, its exported
fields changed, `full_every_n` incremental runs happened since the last full one, or the
previous run is older than `HOURS_UNTIL_TRASH_PERMANENTLY_DELETED` (rows permanently
deleted in between could not be reported otherwise). Schedule at least that often; the
schedule's `warnings` say when the cron expression does not.

For example, with DuckDB:

```sql
SELECT * FROM read_parquet(
  's3://baserow-lake/tables/workspace=1/database=12/table=34/schedule=3/mode=full/*/part-*.parquet',
  hive_partitioning = true
);
```

### Performance and limits

* Rows are read in chunks of `BASEROW_DATA_EXPORT_CHUNK_SIZE` from one consistent
  snapshot and written to `BASEROW_DATA_EXPORT_TMP_DIR` before upload; size that
  directory for the largest table.
* Incremental exports filter on `updated_on`, which is not indexed by default. On large
  tables run `./baserow create_updated_on_indexes [--table-id <id>]`.
* Values of formula, lookup and rollup fields that change because a *referenced* row
  changed do not always move `updated_on`; the periodic full export (`full_every_n`)
  brings them up to date.
* Decimal columns use 38 digits of precision, the maximum most Parquet readers support.

See [Configuration](configuration.md#backup-and-contents-api-configuration) for every
related environment variable.
