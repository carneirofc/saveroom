# web-frontend

## Purpose

Nuxt/Vue browser UI for databases, Application Builder, Automation, Dashboards and admin.

## Ownership

Everything under `web-frontend/`. `modules/core/` is the shared shell; `modules/{database,builder,automation,dashboard,integrations}/` mirror the backend `contrib` domains.

## Local Contracts

No nested lists in this file: prettier indents them differently in CI (no `.editorconfig` there).

### General

- yarn manages packages; Node is pinned by `.nvmrc`.
- Extend through module registries, not hardcoding. Keep in sync with the backend API (serializers, error codes, URLs).
- Every backend permission manager returning data from `get_permissions_object` needs a frontend `permissionManager` of the same type (`modules/core/permissionManagerTypes.js`); unknown types are silently skipped.
- The `prod` image ships only `.output`, never `node_modules` (keeps Go-built esbuild out of the scanned image).
- Destructive one-click actions use `components/modals/ConfirmModal.vue` (`ask({ title, message, confirmLabel, onConfirm })`).

### i18n

- User-facing strings go through i18n. `config/locales.js` (`en`, `pt-BR`) is the single language list, equal to backend `LANGUAGES`; every `locales/` dir needs a JSON file per code (`{}` suffices) or the build fails. Keep `modules/core/moment.js` locales matching.
- Plural messages using `{n}` take the count as the plural argument (`$t(key, n)`), not `{ count }`.
- The product name is never a literal: locale strings use `@:{'app.name'}` (brace form, enforced by `test/unit/core/branding/appName.spec.js`); components outside i18n use `$branding.appName`.

### Branding

- Runtime branding must work without a rebuild: `modules/core/server/branding/` serves `/_branding/{theme.css,config.json,assets/…}` from `BASEROW_BRANDING_DIR` with bundled fallbacks; `plugins/branding.js` applies it during SSR and re-applies `app.name` after language switches.
- Anything branding may override loads through `/_branding/assets/`, never a bundled import or public path.
- `branding.json` values are validated server-side; keep that when adding settings.
- Links come from `$branding` (`appName`, `siteUrl`, `docsUrl`, `siteTitle`, `showAttribution`); never hardcode a project URL. `PROJECT_CREDITS` in `components/version/BuildInfo.vue` can be hidden via `showAttribution` but not overridden.

### Styles and icons

- Color tokens in `assets/scss/colors.scss` are CSS variables: never apply Sass color functions to `$palette-*`/`$color-*`; use `alpha()` or `color-mix()`. No hex colors outside `colors.scss` (except `color_picker.scss` gradients and builder-theme fallbacks).
- Only the Sass `import` deprecation is silenced; fix others.
- `iconoir-*` classes must exist in the installed iconoir version (missing ones render blank).

### Feature notes

- `DownloadLink` preflights downloads with `HEAD` and maps 410 (expired) and 500/503 (server storage, never "not found"). Bind it to `download_url`, never `url`; user file attachments still use `url`.
- Retention/expiry values the UI shows are mirrored from Django settings: default in `modules/core/module.js`, remap in `env-remap.mjs`, and the env var passed to the web-frontend service in `docker-compose.yml`. Non-positive means cleanup off (show nothing). Staff-only limits come from `/admin/limits/`.
- Build metadata (`$buildInfo`) is baked from `BASEROW_BUILD_*` args; `env-remap.mjs` maps them only when non-empty. Empty means a dev build and renders nothing. Backend build (`/admin/build/`) is shown separately; a commit mismatch warns, a failed request shows "could not be read".
- Job elapsed time (`utils/job.js`, `mixins/jobElapsed.js`, `JobDuration.vue`) ticks on its own 1s interval; use it only next to job-only progress bars.
- Backup tabs (`components/backups/*Tab.vue`) take an optional `service` factory so member and staff admin surfaces share them; extend the prop rather than forking. Member restore is gated on `workspace.create_application`, schedule actions on ownership/admin/staff. Use `BackupList`/`BackupListItem` for rows. `Button.vue` has no native `type`: Save is a plain submit, Cancel needs `@click.prevent`.
- API clients (`components/apiClients/`): `scopes.js` mirrors backend `ALL_SCOPES`. A key's secret exists only in the create response; never store it. Revoking updates the row in place.
- CrudTable filters: a blank filter must be absent (`omitEmptyFilters`); anything replaying a CrudTable request reuses `serializeSorts`.
- Protected editing (`modules/database/utils/editConfirmation.js`): single edits are staged in `pendingRowChanges` and saved by `PendingChangesBar`; every other row mutation awaits `confirmDataChange`. `ImportFileModal` uses its own `ConfirmImportModal`, refuses while changes are staged, and gates `replace`/`delete_unmatched` on `database.table.replace_rows`.

## Work Guidance

- `just frontend <recipe>` (`just f`): `lint`, `fix`, `test`, `run-dev-server`, `storybook`, `build-nuxt`. Update snapshots (`just frontend update-snapshots`) only intentionally.
- Relevant skills: `write-frontend-unit-test`, `add-update-builder-element-type`, `create-in-app-notification`.

## Verification

- `just frontend test` and `just frontend lint` (also pre-commit).
- CI `web-frontend-prod-image` builds `prod`, asserts no esbuild artefact, and boots it against `/_health/`.

## Child DOX Index

None.
