# backend

## Purpose

Django backend: REST API, WebSocket layer, Celery workers, and the domain logic for databases, Application Builder, Automation, Dashboards and integrations.

## Ownership

Everything under `backend/`.

- `src/baserow/core/` — registries, permissions, jobs, import/export, backups, scheduling (`core/scheduling/`), auth/SSO, audit log, formulas, notifications.
- `src/baserow/contrib/` — `database/` (incl. `access/` grants and `data_export/` Parquet datalake exports), `builder/`, `automation/`, `dashboard/`, `integrations/`.
- `src/baserow/api/` — DRF serializers, views, URLs, errors. `src/baserow/config/` — settings, Celery, Gunicorn.

## Local Contracts

### Architecture

- uv manages the venv at repo-root `.venv`; never call `pip`.
- Layers: model → handler (persistence/domain) → service (permission-aware) → action (undoable) → API view. `contrib/automation/` is the reference pattern.
- New behavior registers into a registry (`baserow.core.registry`); don't hardcode types.
- Every schema change needs a forward-compatible migration. Never remove a `Params` field of a registered action type (stored params must still deserialize; e.g. `CreateUserActionType.Params.with_invitation_token`).
- Tests reuse fixtures from `test_utils/fixtures/`.
- `core/sso/oidc/config.py`, `core/roles/config.py` and `core/data_destinations/config.py` are imported while settings evaluate: stdlib + `django.core.exceptions` only.

### Auth, SSO and membership

- SSO is env-only: `BASEROW_OIDC_PROVIDERS` is the source of truth; the DB row per provider is only a user-linkage anchor. No admin UI/API for providers.
- The IdP defines only global profiles via client roles (`user_roles`, `staff_roles`, `superuser_roles`); a provider mapping any role refuses users holding none, before provisioning. Never add workspace-scoped IdP mappings (`workspace_mappings`, `team_mappings`, `strict_membership` are refused at startup).
- The OIDC callback fails closed unless `state`, PKCE S256 verifier and nonce match the session and userinfo `sub` equals the ID token's. `require_verified_email` (default true) refuses unverified emails. Keep these in `core/sso/oidc/handler.py`.
- Existing accounts blocked by the different-provider guard (`auth_provider_types.py`) link only via `core/sso/oidc/linking.py` (opt-in `link_existing_accounts`, verified email, never staff/superuser) or the `link_oidc_account` command.
- SSO refresh tokens get the provider's `session_lifetime_minutes` (default 480) and are never re-issued on refresh.
- Keep `SsoErrorCode` (`core/sso/utils.py`) in sync with `loginError` keys in `web-frontend/modules/core/locales/en.json`.
- Workspace membership comes only from admins adding existing users (search ≥3 chars, excludes deactivated/to-be-deleted). No invitations, invite emails or invite-token signups.

### Permissions

- `contrib/database/access/`: `DatabaseAccessGrant` gives a member or `core.teams.Team` a level (`none`/`viewer`/`editor`/`builder`) on workspace default, database or table. Most specific scope wins (table → database → workspace); user grant beats team grants; highest team level wins; no grant falls through to full member access. `database_access` sits right after `member` in `PERMISSION_MANAGERS`. Unlisted operations in `access/levels.py` are builder-only. `filter_queryset` must exclude exactly what checks deny (parity test). Denials must subclass `PermissionDenied`.
- `StaffBypassPermissionManagerType` (`staff_bypass`, after `staff`, before `member`) grants staff the `STAFF_BYPASS_OPERATIONS` on any workspace and never denies. Add cross-workspace staff access there, never to `StaffOnlyPermissionManagerType.STAFF_ONLY_OPERATIONS` (which denies every non-staff actor). Its `filter_queryset` leaves applications unfiltered for staff.
- API clients: `HasApiClientScope` enforces scopes (tuple = all required) and workspace. A view declaring `api_client_scopes` must resolve its workspace via `get_api_client_workspace_id` or a `workspace_id` kwarg, or set `api_client_workspace_independent = True`.

### Audit log

- `core/audit_log/` is permanent and staff-only, fed by `action_done` plus explicit sign-out/failed-sign-in hooks (JWT auth, so Django login signals never fire). Separate from `core.action.Action`; no purge task may touch it.
- A new `log_auth_event` caller must be added to `AUTH_EVENT_TYPES`. Filter options come from the registry, never a `DISTINCT` over entries.

### Files, exports and backups

- `BASEROW_DATA_DESTINATIONS` (S3/Azure/filesystem) is env-only and holds all credentials; models and APIs reference destinations by `name` and never persist or return credentials or locations.
- Exports and backups download through `api/download/` via `download_url` (short-lived `TimestampSigner` token, salt `baserow.export.download`); `url` is a deprecated direct storage link. Views re-run handler scoping and check the token's type and object id. `stream_file_from_storage` must set `Content-Length` explicitly. Every endpoint answers `HEAD`.
- Download errors: `ERROR_EXPORT_FILE_EXPIRED` (410), `ERROR_EXPORT_FILE_MISSING_FROM_STORAGE` (500), `ERROR_STORAGE_UNAVAILABLE` (503). Storage config is shown only to staff; paths and exceptions stay in logs.
- An export that cannot be read back from storage fails instead of finishing.
- `SharedFileStorageHealthCheck` probes web vs. worker filesystem drift (written from the `export` queue); registered only for filesystem storage.
- Remote backups (`core/backups/destination.py`): archive first, `.zip.json` sidecar last; the sidecar is the completion marker, restores verify its sha256. Retention filters on sidecar `instance_id` and `schedule_id`; non-staff restores require this instance and export access to the workspace; non-admins see only their own. Failed sidecar writes delete the archive; sidecar-less archives older than 24h are swept. `restore_remote_backup` does download/checksum/create outside transactions (views not `@transaction.atomic`). Trusting a backup's signing key is staff-only and opt-in (`allow_trust_public_key`).
- Scheduled backups always use `ExportApplicationsToDestinationJobType` (empty `destination` for local) so local retention can filter on `backup_schedule`.
- Backup and datalake schedules run as their owner; update/delete/run need owner, workspace admin or staff (`can_manage_schedule`). Schedules of inactive/to-be-deleted owners are disabled.
- Datalake exports write parts → `_manifest.json` → `_SUCCESS`; the watermark advances only after `_SUCCESS`. Password and form edit-link fields are never exported; unmapped field types fall back to JSON (`data_export/parquet/types.py`).
- Any code that trashes, restores or bulk-updates rows must bump `updated_on` (`update()`/`update_fields` skip `auto_now`).

### Rows and tables

- Table file imports are planned only by `contrib/database/rows/import_planner.py`, consumed by import and preview. Ambiguous keys refuse unless `allow_ambiguous_matches`. Destructive imports (`is_destructive_import`) need `database.table.replace_rows` (builder-only), checked in the view, preview handler and `FileImportJobType.prepare_values`.
- `Table.require_edit_confirmation` is frontend-only: never enforce it server-side. It must round-trip through export/import.
- `FilterableViewMixin.apply_filters` treats `None` and `""` as absent (not a falsiness test, so `"0"` filters).

### Settings and branding

- `DATA_UPLOAD_MAX_MEMORY_SIZE` (`BASEROW_MAX_REQUEST_BODY_SIZE_MB`) caps JSON bodies; keep it well above `BASEROW_MAX_IMPORT_FILE_SIZE_MB`.
- `api/admin/limits/` is read-only (limits come from env). Limits the UI shows next to data are mirrored into web-frontend runtime config; keep defaults in sync with `web-frontend/modules/core/module.js`.
- `api/admin/build/` reports `BASEROW_BUILD_{VERSION,COMMIT,DATE}`, all optionally blank. `baserow.version.VERSION` tracks upstream, not this fork's build.
- Product name is `settings.BRANDING_APP_NAME` (`BASEROW_BRANDING_APP_NAME`, default `Saveroom`); never hard-code one in user-facing strings. The email logo loads from `/_branding/assets/img/logo.svg`.
- `LANGUAGES` (`en`, `pt-BR`) must equal `web-frontend/config/locales.js`; changing it needs a migration resetting dropped profile languages. `just backend make-translations` regenerates only `en`.

## Work Guidance

- `just backend <recipe>` (`just b`): `lint`, `fix`, `test`, `run-dev-server`. Lint is ruff; types via mypy.
- Relevant skills: `manage-backend-layers`, `baserow-registry`, `manage-permissions`, `create-update-service`, `runtime-formulas`, `write-backend-unit-test`, `add-django-config-env-var`.

## Verification

- `just backend test` and `just backend lint` (also pre-commit).

## Child DOX Index

None.
