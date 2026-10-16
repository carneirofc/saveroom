# Single sign-on with OpenID Connect (OIDC)

Saveroom signs users in through any OpenID Connect provider — Keycloak/RHBK, Authentik,
Zitadel, Entra ID, Okta and so on — configured entirely through environment variables.
There is no admin UI and no provider row to manage: the environment is the source of truth.

The IdP decides **who someone is at instance level**, through roles it puts in the token:

* **User** — may sign in and gets an account.
* **Staff** — the Saveroom admin area, instance-wide.
* **Superuser** — staff plus superuser-only actions.

Everything inside a workspace — who is a member, who administers it, teams, and what
members can do with each database and table — is managed **in the app** by workspace
admins. New workspaces therefore need no IdP or environment change.

A user holding none of the mapped roles is refused at login, and no account is created.

This page is the full reference. For a click-by-click Keycloak walkthrough with
day-to-day operations and hardening, see
[Single sign-on with RHBK/Keycloak](sso-rhbk-keycloak.md).

## Contents

* [Environment variables](#environment-variables)
* [Registering Saveroom with the IdP](#registering-saveroom-with-the-idp)
* [Provider reference](#provider-reference)
* [Global profiles](#global-profiles)
* [Workspace access in the app](#workspace-access-in-the-app)
* [How access is decided on each login](#how-access-is-decided-on-each-login)
* [Complete example](#complete-example)
* [Passing the configuration to Saveroom](#passing-the-configuration-to-saveroom)
* [Configuring RHBK/Keycloak](#configuring-rhbkkeycloak)
* [Login error codes](#login-error-codes)
* [Upgrading from workspace mappings](#upgrading-from-workspace-mappings)
* [Security notes](#security-notes)
* [Troubleshooting](#troubleshooting)

## Environment variables

| Variable | Default | Purpose |
| --- | --- | --- |
| `BASEROW_OIDC_PROVIDERS` | `[]` | JSON list of providers. See [Provider reference](#provider-reference). |
| `BASEROW_OIDC_ONLY` | `false` | OIDC-only mode for normal users: password signup is disabled, password login is refused for non-staff accounts and the login page shows only the SSO buttons. A staff/superuser account can still use the password form through **display password login**, so an IdP outage cannot lock you out. Create that break-glass account **before** turning this on. |
| `BASEROW_ALLOW_MULTIPLE_SSO_PROVIDERS_FOR_SAME_ACCOUNT` | unset | When set, an account created through one method (password, another provider) may also sign in through this provider. Leave unset unless you need it; see [Security notes](#security-notes). |

`BASEROW_OIDC_PROVIDERS` is parsed and validated **once, at startup**:

* An invalid value stops the backend from starting with an `ImproperlyConfigured` error
  naming the offending entry and key — it never fails later at login.
* **Every change needs a backend restart** (and the Celery workers, which share the
  settings).
* Issuer discovery needs the network and happens at login, and is logged.

## Registering Saveroom with the IdP

Whatever the provider, register Saveroom as a client with these properties:

| Setting | Value |
| --- | --- |
| Client type | Confidential (Saveroom authenticates with a client secret) |
| Flow | Authorization code (standard flow). Implicit, password and client-credentials grants are unused. |
| Redirect / callback URI | `<BASEROW_PUBLIC_URL>/api/sso/oidc/callback/<name>/` — `<name>` is the provider's `name`, and the trailing slash is required. Example: `https://baserow.example.com/api/sso/oidc/callback/rhbk/` |
| PKCE | `S256`. Saveroom always sends a PKCE challenge; enforcing it on the IdP is recommended. |
| Scopes | `openid`, `email`, `profile` (the default) |
| ID token signing | RSA (`RS256` and friends) — the key is looked up in the IdP's JWKS by `kid` |

What Saveroom needs from the IdP at runtime:

* **Discovery.** Saveroom fetches `<issuer>/.well-known/openid-configuration` and uses its
  `issuer`, `authorization_endpoint`, `token_endpoint`, `userinfo_endpoint` and `jwks_uri`.
  The backend itself makes these calls, server to server, so it must reach the IdP over the
  network and trust its TLS certificate.
* **An ID token** whose signature, `iss` (must equal the discovered issuer), `aud` (must
  contain `client_id`), `exp`, `iat`, `sub` and `nonce` all verify.
* **A userinfo response** whose `sub` equals the ID token's `sub`, and which carries the
  email claim.
* **An email address**, and — unless `require_verified_email` is `false` — an
  `email_verified` claim that is exactly `true` (read from userinfo, falling back to the
  ID token).
* **Roles** under `roles_claim`, in the ID token, the userinfo response, or both.

## Provider reference

Each element of `BASEROW_OIDC_PROVIDERS` is an object with these keys.

### Identity and connection

| Key | Required | Default | Description |
| --- | --- | --- | --- |
| `name` | yes | — | Stable slug: letters, digits, `-` and `_` only, unique across providers. Appears in the callback URL and links Saveroom accounts to this provider, so do not rename it once users have signed in. |
| `display_name` | no | `name` | Label on the login button. |
| `issuer` | yes | — | The provider's issuer URL (`http` or `https`), without `/.well-known/openid-configuration`. |
| `client_id` | yes | — | Client id registered in the IdP. Also the expected ID token audience. |
| `client_secret` | yes | — | Client secret. |
| `scopes` | no | `["openid", "email", "profile"]` | Requested scopes. Must include `openid`. |

### Claims

| Key | Default | Description |
| --- | --- | --- |
| `email_claim` | `email` | Claim in the userinfo response holding the email address. Accounts are matched by email. |
| `name_claim` | `name` | Claim in the userinfo response holding the display name. Falls back to the email when empty. |
| `roles_claim` | `resource_access.${client_id}.roles` | Claim path holding the user's roles. See below. |

`roles_claim` rules:

* It is a **dotted path** into the claims: `resource_access.baserow.roles` reads
  `{"resource_access": {"baserow": {"roles": [...]}}}`.
* `${client_id}` is replaced with the provider's `client_id`, so Keycloak's default mapper
  claim name can be pasted in verbatim.
* A literal dot inside a claim name is escaped as `\.` (in JSON: `"\\."`). If the dotted
  walk does not resolve, the whole string is also tried as one flat key.
* The value may be a list of strings or a single string. Anything else counts as no roles.
* Roles are read from **both** the ID token and the userinfo response, and unioned.

Common values:

| IdP | `roles_claim` |
| --- | --- |
| Keycloak/RHBK client roles | `resource_access.${client_id}.roles` (default) |
| Keycloak/RHBK realm roles | `realm_access.roles` |
| Keycloak group membership mapper, Authentik, Zitadel/Okta custom claim | `groups` (or whatever the mapper emits) |
| Entra ID app roles | `roles` |

The rest of this page says "client role" for whatever strings `roles_claim` yields.

### Profile mapping

| Key | Default | Description |
| --- | --- | --- |
| `user_roles` | `[]` | Roles whose holders may sign in as regular users. |
| `staff_roles` | `[]` | Roles whose holders become Saveroom **staff** (and may sign in). |
| `superuser_roles` | `[]` | Roles whose holders become Saveroom **superuser**, which also implies staff (and may sign in). |

A user needs **at least one** role from any of the three lists. Staff and superuser holders
do not also need a `user_roles` entry.

### Session and verification

| Key | Default | Description |
| --- | --- | --- |
| `require_verified_email` | `true` | Refuse users whose `email_verified` claim is not `true` (`errorEmailNotVerified`). Set `false` only when the IdP's email addresses are authoritative, for example LDAP/AD-federated. |
| `link_existing_accounts` | `false` | When `true`, an existing account created by another method (password, another provider) is linked to this provider on first sign-in instead of being refused with `errorDifferentProvider` — only when the IdP sends `email_verified: true` (even with `require_verified_email: false`), and never for staff or superuser accounts. See [Recovering locked-out accounts](#recovering-locked-out-accounts). |
| `session_lifetime_minutes` | `480` | Lifetime of a session started through this provider. Once it ends the user signs in again, which is when profile changes apply. Positive integer, or `null` to use `BASEROW_REFRESH_TOKEN_LIFETIME_HOURS`. |

### Refused keys

Keys from older configurations are refused at startup, because silently ignoring them would
drop the access they used to grant:

| Key | What to do |
| --- | --- |
| `groups_claim` | Rename to `roles_claim`. |
| `staff_groups` | Rename to `staff_roles`. |
| `superuser_groups` | Rename to `superuser_roles`. |
| `workspace_mappings`, `team_mappings`, `strict_membership` | Remove. Add members, teams and access in the app. See [Upgrading from workspace mappings](#upgrading-from-workspace-mappings). |

`BASEROW_ROLES` and the `sync_roles` command no longer exist; the variable is ignored.

## Global profiles

| Profile | Granted by | What it allows |
| --- | --- | --- |
| Superuser | `superuser_roles` | Everything staff can do, plus superuser-only admin actions. Always also staff. |
| Staff | `staff_roles` | The admin area: instance settings, users, all workspaces, application-type toggles, and managing access in any workspace. |
| User | `user_roles` | Signing in. Only the workspaces they are added to, and creating workspaces when the instance allows it. |

Staff and superuser are **reconciled on every login through this provider**: granted when
the user holds a mapped role, revoked when not. Only the dimension you configure is touched —
a provider with no `staff_roles` never changes anyone's staff flag. A local admin who never
signs in through SSO is never modified.

## Workspace access in the app

Once signed in, a user has no workspace until someone adds them. All of this is done by the
workspace's admins, or by staff — the full guide is
[Managing workspace access](workspace-access.md):

| Task | Where |
| --- | --- |
| Add people who already signed in | *Workspace settings → Members → Add members* — search by name or email (at least 3 characters) and pick `MEMBER` or `ADMIN`. |
| Add someone who has not signed in yet | Ask them to sign in once, then add them. |
| Promote or demote a workspace admin | The role column in the members list. |
| Group members | *Workspace settings → Teams*. |
| Restrict databases and tables | *Manage access* in the context menu of a database or table, or *Workspace default access* on the Teams page. Staff: *Admin → Workspaces → Manage default access*. |

Access levels, per member or team:

| Level | Allows |
| --- | --- |
| No access | The database or table is hidden. |
| Viewer | Read rows, fields and views; export. |
| Editor | Viewer, plus create, update and delete rows. |
| Builder | Editor, plus fields, views, filters, webhooks and the table or database itself. |

For a `MEMBER`, the most specific scope with a level decides: table, then database, then the
workspace default. A level given to the member directly beats their teams' levels; between
teams the highest wins. With no level anywhere the member has full member access. Workspace
`ADMIN`s are never restricted. Changes apply immediately, without signing in again.

## How access is decided on each login

1. **Verify.** `state`, PKCE verifier, ID token (signature, issuer, audience, expiry,
   nonce) and userinfo `sub` must all check out, otherwise `errorAuthFlowError`. A missing
   email is also `errorAuthFlowError`; an unverified one is `errorEmailNotVerified`.
2. **Collect roles** from `roles_claim` in the ID token and userinfo, unioned.
3. **Deny by default.** If the provider maps any role (`user_roles`, `staff_roles` or
   `superuser_roles`) and the user holds none of them, the login is refused with
   `errorNoMappedRole` — **before** an account is created. A provider that maps no role at
   all is not gated: every IdP user may sign in.
4. **Find or create the account** by email. New accounts are provisioned automatically,
   even when the instance has new signups disabled and even with `BASEROW_OIDC_ONLY`. An
   existing account created by another method is refused with `errorDifferentProvider`,
   unless the provider sets `link_existing_accounts` (verified email, non-staff accounts
   only — the account is then linked) or
   `BASEROW_ALLOW_MULTIPLE_SSO_PROVIDERS_FOR_SAME_ACCOUNT` is set. A deactivated
   account is refused with `errorUserDeactivated`.
5. **Reconcile staff and superuser**, grant and revoke.
6. **Start a session** bounded by `session_lifetime_minutes`.

Workspace memberships are never touched by a login. Removing a role in the IdP does not end
a session that is already open; it applies when the session expires and the user signs in
again. To cut access immediately, disable the user in the IdP **and** deactivate the account
in Saveroom's admin area.

## Complete example

Scenario: company staff through Keycloak, partners through a second IdP.

| Provider | Role in token | Profile |
| --- | --- | --- |
| `rhbk` (Keycloak client roles) | `baserow-superusers` | superuser |
| | `baserow-staff` | staff |
| | `baserow-user` | user |
| `partners` (generic IdP, `groups` claim) | `baserow-partner` | user |

`BASEROW_OIDC_PROVIDERS` — every key shown, defaults written out explicitly:

```json
[
  {
    "name": "rhbk",
    "display_name": "Company SSO",
    "issuer": "https://keycloak.example.com/realms/main",
    "client_id": "baserow",
    "client_secret": "change-me-rhbk-secret",
    "scopes": ["openid", "email", "profile"],
    "email_claim": "email",
    "name_claim": "name",
    "roles_claim": "resource_access.${client_id}.roles",
    "user_roles": ["baserow-user"],
    "staff_roles": ["baserow-staff"],
    "superuser_roles": ["baserow-superusers"],
    "require_verified_email": true,
    "link_existing_accounts": false,
    "session_lifetime_minutes": 480
  },
  {
    "name": "partners",
    "display_name": "Partner login",
    "issuer": "https://idp.partners.example.org/application/o/baserow/",
    "client_id": "baserow-partners",
    "client_secret": "change-me-partner-secret",
    "roles_claim": "groups",
    "user_roles": ["baserow-partner"],
    "session_lifetime_minutes": 240
  }
]
```

Notes on this configuration:

* The `partners` provider maps no staff or superuser roles, so it never makes anyone staff,
  and it never revokes a staff flag granted through `rhbk` either.
* Partners land in no workspace. A workspace admin adds them where they collaborate and
  restricts them with access levels, for example a *Partners* team with *No access* as
  workspace default and *Editor* on the shared tables.

Rollout order:

1. Create the roles and assignments in each IdP.
2. Set `BASEROW_OIDC_PROVIDERS` and restart.
3. Sign in with one test user per profile, plus one with no mapped role (must be refused).
4. Have workspace admins add the signed-in users to their workspaces.

## Passing the configuration to Saveroom

The value is JSON, so the only difficulty is quoting. Store it compacted to one line where
the format requires it, and keep secrets out of version control.

### `docker run`

`--env-file` takes each value literally up to the end of the line — no quotes, no line
breaks:

```bash
# baserow-sso.env
BASEROW_OIDC_PROVIDERS=[{"name":"rhbk","display_name":"Company SSO","issuer":"https://keycloak.example.com/realms/main","client_id":"baserow","client_secret":"change-me","user_roles":["baserow-user"],"staff_roles":["baserow-staff"]}]
BASEROW_OIDC_ONLY=true
```

```bash
docker run -d --name baserow \
  -e BASEROW_PUBLIC_URL=https://baserow.example.com \
  --env-file baserow-sso.env \
  -v baserow_data:/baserow/data -p 80:80 -p 443:443 \
  ghcr.io/carneirofc/saveroom:latest
```

Compact a pretty-printed file with `jq -c . providers.json`.

### Docker Compose

The root [`docker-compose.yaml`](../../docker-compose.yaml) passes `BASEROW_OIDC_PROVIDERS`
and `BASEROW_OIDC_ONLY` through from `.env`. Wrap the JSON value in single quotes on one
line:

```bash
# .env
BASEROW_OIDC_PROVIDERS='[{"name":"rhbk","issuer":"https://keycloak.example.com/realms/main","client_id":"baserow","client_secret":"change-me","user_roles":["baserow-user"],"staff_roles":["baserow-staff"]}]'
BASEROW_OIDC_ONLY=true
```

Then `docker compose up -d` to recreate the containers with the new values.

### Helm

Set the variables through `extraEnv`; a block scalar keeps the JSON readable:

```yaml
extraEnv:
  BASEROW_OIDC_ONLY: "true"
  BASEROW_OIDC_PROVIDERS: |
    [{"name": "rhbk", "display_name": "Company SSO",
      "issuer": "https://keycloak.example.com/realms/main",
      "client_id": "baserow", "client_secret": "change-me",
      "user_roles": ["baserow-user"],
      "staff_roles": ["baserow-staff"]}]
```

> `extraEnv` is rendered into the chart's ConfigMap, which is not encrypted, and
> `client_secret` lives inside the JSON. Restrict who can read ConfigMaps in the
> namespace, keep the values file out of version control (or encrypt it, for example with
> SOPS), and rotate the secret if it leaks. The pods pick up changes on `helm upgrade`.

## Configuring RHBK/Keycloak

Condensed setup for Red Hat build of Keycloak and upstream Keycloak (same console paths).
The [full RHBK/Keycloak guide](sso-rhbk-keycloak.md) walks through each screen, and covers
onboarding and offboarding, secret rotation, hardening, and a declarative realm import.

The issuer is `https://<keycloak-host>/realms/<realm>`.

1. **Create the client.** **Clients → Create client**:
   * Client type `OpenID Connect`, Client ID `baserow`.
   * **Client authentication** on; **Standard flow** on, other flows off.
   * **Valid redirect URIs**: `https://baserow.example.com/api/sso/oidc/callback/rhbk/`
     (`rhbk` = provider `name`).
   * **Advanced → Advanced settings → Proof Key for Code Exchange Code Challenge Method**:
     `S256`.
   * Copy the secret from **Credentials**.
2. **Create client roles.** **Clients → baserow → Roles → Create role**: `baserow-user`,
   `baserow-staff`, `baserow-superusers`. Saveroom reads **client** roles by default, not
   realm roles.
3. **Assign roles through groups.** **Groups → Create group** (e.g. `baserow-users`), then
   **Role mapping → Assign role → Filter by clients** and pick the `baserow` roles — the
   default filter lists only realm roles. Add users under **Members**.
4. **Put client roles in the ID token and userinfo.** Keycloak's built-in client roles
   mapper adds them to the access token only, and Saveroom reads the ID token and
   userinfo. On **Clients → baserow → Client scopes → `baserow-dedicated` → Add mapper →
   By configuration → User Client Role**:

   | Field | Value |
   | --- | --- |
   | Name | `baserow client roles` |
   | Client ID | `baserow` |
   | Token Claim Name | `resource_access.${client_id}.roles` |
   | Claim JSON Type | `String` |
   | Multivalued | On |
   | Add to ID token | **On** |
   | Add to userinfo | **On** |
   | Add to access token | On |

   If **Full scope allowed** is off on the client, also add the roles under its **Scope**
   tab.
5. **Verify the claim.** **Clients → baserow → Client scopes → Evaluate**, pick a user,
   open **Generated ID token**, and look for:

   ```json
   "resource_access": { "baserow": { "roles": ["baserow-user"] } }
   ```

6. **Check email verification.** Users need `email_verified: true`. For LDAP/AD
   federation, enable **Trust Email** on the user federation provider; otherwise verify
   users' emails or set `require_verified_email: false`.
7. **Keep self-registration off** in **Realm settings → Login**, since Saveroom links
   accounts by email.
8. **Configure Saveroom** with the `rhbk` provider from the
   [complete example](#complete-example) (the default `roles_claim` already matches step 4)
   and restart.
9. **Test** with one user per group and one user in no group — the latter must land on
   `/login?error=errorNoMappedRole` and no account may appear in the admin area.

To map **realm roles** instead, set `"roles_claim": "realm_access.roles"` and enable
**Add to ID token** / **Add to userinfo** on the realm roles mapper. To map Keycloak
**groups** directly, add a **Group Membership** mapper with Token Claim Name `groups`,
**Full group path** off, ID token and userinfo on, and set `"roles_claim": "groups"`.

## Login error codes

A failed login redirects to `/login?error=<code>`, and the backend log has details.

| Code | Cause | Fix |
| --- | --- | --- |
| `errorNoMappedRole` | The provider maps roles and the user holds none of them — or the roles never reached Saveroom. | Check the token contents (for Keycloak: **Evaluate**, step 5 above); check `roles_claim`; assign the user a mapped role. |
| `errorEmailNotVerified` | `require_verified_email` is on and `email_verified` is not `true`. | Verify the email in the IdP, trust federated emails, or set `require_verified_email: false`. |
| `errorAuthFlowError` | Discovery or JWKS unreachable; token signature/issuer/audience/nonce check failed; userinfo `sub` mismatch; no email returned; `state`/PKCE mismatch; the IdP returned no code. | Read the backend log. Check network and TLS trust to the issuer, the exact `issuer` string, `client_id`, the redirect URI, and the client's PKCE method. |
| `errorProviderDoesNotExist` | The callback or login URL names a provider not in `BASEROW_OIDC_PROVIDERS`. | Match the redirect URI's `<name>` to the provider `name`; restart after config changes. |
| `errorDifferentProvider` | An account with this email exists under a different sign-in method. | Expected protection. Link the account with the `link_oidc_account` command, or set `link_existing_accounts` on the provider. See [Recovering locked-out accounts](#recovering-locked-out-accounts). |
| `errorUserDeactivated` | The Saveroom account is deactivated. | Reactivate it in the admin area. |
| `errorSignupDisabled` | The signup layer refused to create the account. SSO provisioning normally bypasses the signup setting, so this indicates an unusual flow. | Check the backend log. |

## Recovering locked-out accounts

`errorDifferentProvider` means the account exists but is not linked to this provider:
it was created with a password or another provider, or the provider's `name` changed
(each `name` has its own links, so a rename locks every user out). Link it with the
`link_oidc_account` management command — no restart needed:

```sh
# Docker Compose (all-in-one image: docker exec baserow ./baserow.sh backend-cmd manage ...)
docker compose exec backend /baserow/backend/docker/docker-entrypoint.sh manage link_oidc_account list alice@example.com
docker compose exec backend /baserow/backend/docker/docker-entrypoint.sh manage link_oidc_account link keycloak --email alice@example.com
# after renaming a provider from "old-name" to "keycloak"
docker compose exec backend /baserow/backend/docker/docker-entrypoint.sh manage link_oidc_account link keycloak --from-provider old-name
docker compose exec backend /baserow/backend/docker/docker-entrypoint.sh manage link_oidc_account unlink keycloak --email alice@example.com
```

`link` requires the provider to be in `BASEROW_OIDC_PROVIDERS` and works for staff
accounts too. To link many regular accounts without operator action, set
`link_existing_accounts: true` on the provider instead.

## Upgrading from workspace mappings

Earlier versions let the IdP place users in workspaces (`workspace_mappings`,
`strict_membership`) and restrict them with `BASEROW_ROLES`. On upgrade:

1. **Before upgrading**, note which roles restricted which members: those restrictions are
   dropped and affected members become unrestricted members.
2. Remove `workspace_mappings`, `team_mappings` and `strict_membership` from each provider
   (the backend refuses to start otherwise) and add a `user_roles` entry listing the roles
   that used to grant a membership, so those users keep signing in. Remove `BASEROW_ROLES`.
3. Existing memberships stay as they are. Restrict members again with teams and access
   levels, and add new people from *Members → Add members*.

## Security notes

* **Accounts are linked by email.** Anyone who can obtain a verified token for an address
  can sign in as the Saveroom account with that address. Keep IdP self-registration off,
  keep `require_verified_email` on unless the IdP's addresses are authoritative, and leave
  `BASEROW_ALLOW_MULTIPLE_SSO_PROVIDERS_FOR_SAME_ACCOUNT` unset.
* **`link_existing_accounts` trusts the IdP with existing accounts.** Enable it only on an
  IdP whose verified emails are authoritative. Staff and superuser accounts are never
  linked automatically; link them with `link_oidc_account`.
* **Deny by default only applies when something is mapped.** A provider with no
  `user_roles`, `staff_roles` or `superuser_roles` lets every user of that IdP create an
  account.
* **Workspace admins can look up accounts.** *Add members* searches every active account by
  name or email (at least 3 characters, at most 20 results). Choose workspace admins
  accordingly.
* **Workspace `ADMIN`s are unrestricted.** They can add members, change permissions and
  manage access; give most people `MEMBER` with access levels instead.
* **Keep a break-glass admin.** A local staff account that signs in with a password is
  never touched by SSO reconciliation, and still works under `BASEROW_OIDC_ONLY`.
* **Set the instance's email verification to "no verification"** (admin settings).
  SSO-provisioned accounts start unverified, and `recommended`/`enforced` would email users
  about an address the IdP already vouches for.
* **Protect the secret.** `client_secret` sits inside `BASEROW_OIDC_PROVIDERS`; treat the
  whole variable as a secret wherever it is stored.

## Troubleshooting

1. **Backend will not start** — read the `ImproperlyConfigured` message; it names the
   provider index and key (for example
   `BASEROW_OIDC_PROVIDERS[0]: 'workspace_mappings' is no longer supported.`).
   Validate syntax with `jq . <<< "$BASEROW_OIDC_PROVIDERS"`.
2. **Config change ignored** — restart the backend and workers.
3. **Issuer reachable?** From inside the backend container:

   ```bash
   curl -fsS "https://keycloak.example.com/realms/main/.well-known/openid-configuration"
   ```

   A failure here is DNS, network or TLS trust, not Saveroom configuration.
4. **Roles in the token?** Inspect the ID token and userinfo in the IdP (Keycloak:
   **Evaluate**) and confirm the path matches `roles_claim`.
5. **Signed in but no workspace** — expected: a workspace admin must add the user in the
   app. Users only appear in *Add members* after their first sign-in.
6. **A member sees too much or too little** — check *Manage access* on the table, its
   database and the workspace default, for the member and each of their teams.

## Related

* [Single sign-on with RHBK/Keycloak](sso-rhbk-keycloak.md) — detailed Keycloak guide.
* [Managing workspace access](workspace-access.md) — members, teams and access levels.
* [Configuration](configuration.md) — every environment variable.
* [Turning application types off instance-wide](instance-settings.md).
* [Installing with Helm](install-with-helm.md).
