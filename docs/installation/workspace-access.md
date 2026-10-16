# Managing workspace access

Who is in a workspace, who administers it, and what each member can do with its databases
and tables are managed inside Saveroom — not by the identity provider and not through
environment variables. Creating a workspace therefore never needs a configuration change or
a restart.

With single sign-on, the IdP only decides who may sign in and who is instance staff; see
[Single sign-on with OpenID Connect](sso-oidc.md). Everything on this page applies the same
way to password accounts.

## Contents

* [Who can do what](#who-can-do-what)
* [Adding members](#adding-members)
* [Teams](#teams)
* [Access levels](#access-levels)
* [How the effective level is decided](#how-the-effective-level-is-decided)
* [Recipes](#recipes)
* [API reference](#api-reference)
* [Troubleshooting](#troubleshooting)

## Who can do what

| Action | Workspace `ADMIN` | Workspace `MEMBER` | Instance staff |
| --- | --- | --- | --- |
| Add existing users, remove members, change `ADMIN`/`MEMBER` | Yes | No | Only in workspaces they belong to as `ADMIN` |
| Create, rename and delete teams, manage team members | Yes | No | Only in workspaces they belong to as `ADMIN` |
| Set access levels on the workspace default, databases and tables | Yes | No | Any workspace, from **Admin → Workspaces** or the API |
| Be restricted by access levels | Never | Yes | Only as a `MEMBER` |

A workspace `ADMIN` always has full access, so keep that permission for the people who
manage the workspace and give everyone else `MEMBER` plus access levels.

## Adding members

*Workspace settings → Members*:

* **Add members** — for people who already have an account (with SSO: who signed in at
  least once). Type at least three characters of their name or email, tick the users, choose
  **Add as** `MEMBER` or `ADMIN`, and confirm. They are added immediately, without an email.
  Deactivated accounts, accounts pending deletion and existing members are never listed, and
  at most 20 matches are shown. Adding someone who is already a member leaves their
  permissions unchanged.
There are no email invitations: a person needs an account (with SSO: signs in once) before
they can be added.

To change `MEMBER`/`ADMIN` later, use the role column of the members list. Removing a member
also removes them from the workspace's teams.

## Teams

*Workspace settings → Teams* groups members so access can be given to many people at once.

* Create a team with a name unique in the workspace.
* Add members from the workspace; a person can be in several teams.
* Renaming a team keeps its members and access levels; deleting it removes both.

Teams hold no access by themselves — give them access levels.

## Access levels

Open **Manage access**:

* on a **database**: its context menu in the sidebar;
* on a **table**: its context menu in the sidebar;
* for the **workspace default**: *Workspace settings → Teams → Workspace default access*, or
  as staff, *Admin → Workspaces → ⋯ → Manage default access*.

Every member and team is listed with a level:

| Level | Allows |
| --- | --- |
| **Inherit** | No level here; the level of the database or workspace default applies. |
| **No access** | The database or table is hidden and every request to it is refused. |
| **Viewer** | Read rows, fields and views; list comments; export. |
| **Editor** | Viewer, plus create, update, move, delete and restore rows, import files, comment, and create personal views. |
| **Builder** | Editor, plus fields, views, filters, sorts, decorations, webhooks, data sync, and changing, duplicating or deleting the table or database. On a database or the workspace default, also creating tables. |

The row under each name shows what it currently inherits, for example *Inherits Viewer from
database*. Workspace admins are listed but cannot be restricted.

Changes apply immediately: affected users' browsers reload their permissions and sidebar,
and they see a notice suggesting a reload.

## How the effective level is decided

For a `MEMBER` working on a table:

1. **The most specific scope with a level wins:** the table, then its database, then the
   workspace default.
2. **Within that scope**, a level given to the member directly beats the levels of their
   teams; between several teams, the **highest** level wins.
3. **No level anywhere:** the member has full member access, exactly as before any level was
   set.

A database set to **No access** still appears, read-only, when the member can access one of
its tables, so that table can be reached. Its other tables stay hidden.

Only databases and tables are covered. Application builder applications, dashboards and
automations follow the member's normal `MEMBER` access.

## Recipes

**Contractors who may only edit one table**

1. Create a team *Contractors* and add the people.
2. *Workspace default access*: *Contractors* → **No access**.
3. On the table: *Contractors* → **Editor**.

They see only that table's database, containing only that table.

**Read-only workspace with one team of builders**

1. *Workspace default access*: every `MEMBER` who should only read → **Viewer**, or put them
   in a team *Readers* → **Viewer**.
2. Create a team *Builders* → **Builder** on the workspace default.

**Hide one sensitive table from everyone but finance**

1. On the table: each team except *Finance* → **No access** (or the members directly).
2. *Finance* keeps inheriting its access, or set it explicitly to **Editor**.

## API reference

All endpoints require a JWT of a workspace `ADMIN` (access endpoints also accept staff).

| Method and path | Purpose |
| --- | --- |
| `GET /api/workspaces/users/workspace/<workspace_id>/candidates/?search=<text>` | Accounts that can be added (`search` at least 3 characters, max 20 results). |
| `POST /api/workspaces/users/workspace/<workspace_id>/` | Add users: `{"user_ids": [1, 2], "permissions": "MEMBER"}`. All or nothing; `ERROR_USERS_CANNOT_BE_ADDED` when any user can't be added. |
| `GET /api/workspaces/teams/workspace/<workspace_id>/` | List teams with their members. |
| `POST /api/workspaces/teams/workspace/<workspace_id>/` | Create a team: `{"name": "Finance", "user_ids": [1]}`. |
| `PATCH /api/workspaces/teams/<team_id>/` | Rename: `{"name": "Ops"}`. |
| `DELETE /api/workspaces/teams/<team_id>/` | Delete the team and its access levels. |
| `POST`/`DELETE /api/workspaces/teams/<team_id>/members/` | Add or remove members: `{"user_ids": [1]}`. |
| `GET /api/database/access/<workspace\|database\|table>/<id>/` | Members and teams with their level on the scope and what they inherit. |
| `PUT /api/database/access/<workspace\|database\|table>/<id>/` | Set levels: `{"grants": [{"subject_type": "team", "subject_id": 3, "level": "viewer"}]}`. `level: null` removes the level (inherit). |

Error codes: `ERROR_TEAM_DOES_NOT_EXIST`, `ERROR_TEAM_NAME_NOT_UNIQUE`,
`ERROR_TEAM_MEMBER_NOT_IN_WORKSPACE`, `ERROR_ACCESS_SCOPE_DOES_NOT_EXIST`,
`ERROR_INVALID_ACCESS_SUBJECT`, plus the usual `ERROR_USER_NOT_IN_GROUP` and
`ERROR_USER_INVALID_GROUP_PERMISSIONS`.

## Troubleshooting

| Symptom | Cause |
| --- | --- |
| A person is missing from **Add members** | They have no account yet (with SSO: never signed in), are deactivated or pending deletion, are already a member, or fewer than three characters were typed. Ask them to sign in once first. |
| A member still sees a table set to **No access** | They are a workspace `ADMIN`, or a more specific level applies — check the table, not only the database, for the member and each of their teams. |
| A member sees nothing after a change | A **No access** workspace default with no level on any table they need. Give the team a level on the database or table. |
| A member can read but not edit | The effective level is **Viewer**; set **Editor** on the same or a more specific scope. |
| Changes don't show up for a user | Their browser reloads permissions over the websocket; if it was offline, a page reload applies them. |
