# ADR 005: IdP defines global profiles, the app manages workspace access

## Status

Accepted — 2026-09-14

## Context

Access used to be decided only by environment and IdP data: OIDC client roles mapped users
to workspace membership (`workspace_mappings`, `ADMIN`/`MEMBER`) and, optionally, to a
workspace-wide operation list declared in `BASEROW_ROLES`. Both referenced numeric
workspace ids in the environment, so every new workspace needed an env change and a
restart. Workspaces are created constantly, and workspace admins could not restrict a
member to some databases or tables.

## Decision

* **The IdP only defines global profiles**, as client roles on the provider:
  `user_roles` (may sign in), `staff_roles` and `superuser_roles`. A provider that maps any
  role still refuses users holding none of them.
* **Removed:** `workspace_mappings`, `team_mappings`, `strict_membership`,
  `BASEROW_ROLES`, `sync_roles`, `core.Role`, `WorkspaceUser.role`, the `granular_role`
  permission manager and the SSO membership tracking. The removed provider keys are refused
  at startup with a message pointing to in-app management.
* **Workspace access is managed in the app** by workspace admins (and staff):
  * members are added directly from users who already signed in;
  * **teams** (`core/teams/`) group members;
  * **access grants** (`contrib/database/access/`) give a member or team a level — `none`,
    `viewer`, `editor`, `builder` — on the workspace default, a database or a table.
* The `database_access` permission manager, placed after `member`, decides database-family
  operations for non-admin members:
  * the most specific scope with a grant wins (table → database → workspace default);
  * within a scope a direct user grant beats team grants, and the highest team level wins;
  * with no applicable grant it passes through, so the member keeps full member access.
* `viewer` and `editor` are explicit operation allow-lists; `builder` is every operation whose
  context lives inside a database, so a newly added operation is builder-only until listed.
* A database whose own level is `none` stays listed (read only) while one of its tables is
  accessible, so that table is reachable.

## Consequences

* New workspaces need no IdP or environment change.
* Upgrading drops granular roles: members that had one become unrestricted members until an
  admin restricts them again with access grants.
* Workspace admins can look up instance users by name or email to add them.
* Listing endpoints must stay consistent with individual checks; `filter_queryset` of the
  manager is covered by a parity test.
* The manager costs no queries for workspaces without grants (cached flag) and a constant
  number of queries per permission batch otherwise.
