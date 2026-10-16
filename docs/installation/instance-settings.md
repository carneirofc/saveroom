# Turning application types off instance-wide

Saveroom ships four kinds of application — databases, applications (the application
builder), dashboards and automations. An instance administrator can turn any of them off,
so that the type stops existing for everyone: nobody can create one, and the ones that
already exist disappear from the interface and from the API.

This is a **whole-instance** switch, in the same sense the SSO guide's
[Administrator means the whole instance](sso-rhbk-keycloak.md#administrator-means-the-whole-instance)
section uses the word. It is not per workspace and not per user. A workspace's own ADMIN
cannot change it; only an account with global staff (`is_staff`) can.

Nothing is deleted. Disabling a type hides its applications and refuses access to them;
their rows stay in the database untouched, and enabling the type again brings everything
back exactly as it was.

## What each toggle does

| Toggle in the admin area | Setting field | What stops working | What is unaffected |
| --- | --- | --- | --- |
| Databases | `enable_database` | Creating a database; opening any existing database, table, view, row or field | Every other application type |
| Application Builder | `enable_builder` | Creating a builder application; opening any existing one, including pages published to a public domain | Every other application type |
| Dashboards | `enable_dashboard` | Creating a dashboard; opening any existing dashboard or its widgets | Every other application type |
| Automations | `enable_automation` | Creating an automation; opening any existing workflow or node | Every other application type |

A disabled type is refused everywhere, not only in the interface:

* It is gone from the **Create new** menu in the sidebar.
* `POST /api/applications/workspace/<id>/` with that type returns `400` with
  `ERROR_APPLICATION_TYPE_DISABLED`.
* `GET /api/applications/workspace/<id>/` leaves its applications out of the response, so
  they vanish from the sidebar on the next page load.
* Any request that reads one of those applications, or anything inside it, returns `401`
  with `PERMISSION_DENIED`.

The refusal applies to template workspaces and to publicly published builder applications
as well — there is no path around it.

## Flipping a toggle

Sign in with a staff account and open **Admin → Settings** (`/admin/settings`). The four
switches sit under **Application features**. A change takes effect immediately for new
requests; open browser sessions pick it up on their next page load.

The same settings are writable through the API:

```jsonc
// PATCH /api/settings/update/
// Authorization: JWT <token of a staff user>
{
  "enable_database": true,      // databases, tables, views, rows
  "enable_builder": false,      // the application builder
  "enable_dashboard": false,    // dashboards and their widgets
  "enable_automation": true     // automation workflows
}
```

Send only the keys you want to change; the rest keep their current value. The response is
the full settings object. `GET /api/settings/` returns the same fields and needs no
authentication, which is how the web frontend knows what to show.

These are database-backed settings, not environment variables. They are stored on the
single `Settings` row, survive restarts, and are shared by every backend and worker
process — there is nothing to redeploy after changing one.

They are also unrelated to the developer `FEATURE_FLAGS` environment variable described
in [Feature flags](../development/feature-flags.md), which gates unfinished features in
development builds.

## Scripting the settings after an install

Because the toggles live in the database, a Docker Compose or Helm deployment cannot set
them through its environment. Apply them once the instance is up, with a staff account:

```bash
BASEROW=https://baserow.example.com

TOKEN=$(curl -s -X POST "$BASEROW/api/user/token-auth/" \
  -H 'Content-Type: application/json' \
  -d '{"email": "admin@example.com", "password": "change-me"}' \
  | jq -r .access_token)

curl -s -X PATCH "$BASEROW/api/settings/update/" \
  -H "Authorization: JWT $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"enable_builder": false, "enable_dashboard": false, "enable_automation": false}'
```

The call is idempotent, so it is safe to run from a post-install job on every deploy. If
the account has two-factor authentication enabled, `token-auth` returns a two-factor
challenge instead of an `access_token`; use a dedicated staff account without it. With
`BASEROW_OIDC_ONLY` set, password login still works for staff accounts (the break-glass
login), so the same script applies.

## Worked example: a database-only instance

An instance that exists to hold structured data, with the builder, dashboards and
automations switched off:

1. Sign in as a staff user and open `/admin/settings`.
2. Under **Application features**, turn off **Application Builder**, **Dashboards** and
   **Automations**. Leave **Databases** on.
3. Reload a workspace. The sidebar now lists databases only, and **Create new** offers
   nothing else.
4. Any dashboards or automations that existed before are hidden, and their API endpoints
   return `PERMISSION_DENIED`. Their data is still on disk.

To reverse it, turn the switches back on. Everything reappears, including the
applications hidden in step 4.

## See also

* [Configuring Saveroom](configuration.md) — environment variables, including the ones
  that must be set before startup.
* [Single sign-on with OpenID Connect](sso-oidc.md) — granting the global staff role
  that can change these settings from your IdP's roles.
* [Single sign-on with RHBK/Keycloak](sso-rhbk-keycloak.md) — driving instance and
  workspace access from Keycloak client roles.
