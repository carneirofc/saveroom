# Single sign-on with Red Hat build of Keycloak (RHBK)

This guide configures Saveroom so that **Keycloak client roles decide who may sign in and
who administers the instance**. Everything inside a workspace — members, workspace admins,
teams and database/table access — is managed in Saveroom by the workspace's admins, so
creating a workspace never needs a Keycloak or environment change. A user holding none of
the mapped client roles is refused at login and no account is created for them.

It then covers how to run that setup day to day — onboarding, granting access, offboarding
and rotating the secret — and how to prove the integration works before handing it to
users.

It applies equally to upstream Keycloak and the Red Hat build (RHBK); the admin console
paths are the same.

For the provider-agnostic reference — every configuration key, a complete multi-provider
example and the login error codes — see
[Single sign-on with OpenID Connect](sso-oidc.md).

## What this guide assumes

Deploying Keycloak itself is out of scope. Before you start you need:

* A **running** Keycloak/RHBK instance, reachable over HTTPS from the Saveroom backend
  (the backend fetches the discovery document and the JWKS itself, server to server).
* An account that can manage clients, roles, groups and users in the target realm.
* The realm you want Saveroom to use, decided. Its issuer URL is
  `https://<keycloak-host>/realms/<realm>` — that exact string is what goes in `issuer`
  below, and Saveroom appends `/.well-known/openid-configuration` to it to discover the
  rest.
* Saveroom's own public URL, since it determines the redirect URI you register in step 1.

## 1. Create the client

In the realm you want Saveroom to use:

1. **Clients → Create client**, client type `OpenID Connect`, Client ID `baserow`.
2. Enable **Client authentication** (Saveroom is a confidential client and uses a secret).
3. Under **Authentication flow**, keep **Standard flow** enabled; the others are unused.
4. Set **Valid redirect URIs** to
   `<BASEROW_PUBLIC_URL>/api/sso/oidc/callback/<name>/`, where `<name>` is the provider
   `name` you will put in `BASEROW_OIDC_PROVIDERS` — for example
   `https://baserow.example.com/api/sso/oidc/callback/rhbk/`.
5. Under **Advanced → Advanced settings**, set **Proof Key for Code Exchange Code
   Challenge Method** to `S256`. Saveroom always sends a PKCE challenge; this makes
   Keycloak refuse any code exchange that lacks one.
6. Copy the secret from the client's **Credentials** tab.

## 2. Define the client roles

Saveroom reads **client** roles (`resource_access.<client_id>.roles`), not realm roles.
On the `baserow` client, open **Roles → Create role** and add one role per profile:

| Client role | What Saveroom will do with it |
| --- | --- |
| `baserow-user` | allow signing in as a regular user |
| `baserow-staff` | grant global staff (admin area) |
| `baserow-admins` | grant global superuser |

These three names are the whole contract between the two systems. Renaming one later means
editing `BASEROW_OIDC_PROVIDERS` and restarting the backend.

### Administrator means the whole instance

Saveroom has two separate notions of privilege, and Keycloak only ever grants the first:

* **Global** — `is_staff` / `is_superuser`. Instance-wide authority: the admin area,
  instance settings, every workspace. Granted by `staff_roles` / `superuser_roles`.
* **Workspace-scoped** — a member's `ADMIN` or `MEMBER` permissions inside one workspace,
  plus teams and access levels. Managed in Saveroom by that workspace's admins (whoever
  created it, or someone they promoted), or by staff.

## 3. Assign the roles through groups

You can assign client roles directly to users, but groups are the shape worth building.
Saveroom reconciles staff and superuser on **every** login, so one group membership becomes
the single lever that both grants and revokes a person's profile.

1. **Groups → Create group**, one per profile — for example `baserow-users`,
   `baserow-staff`.
2. Open the group, go to **Role mapping → Assign role**, then switch the filter to
   **Filter by clients** and pick the `baserow` role. This filter is the step people
   miss: the default view lists only realm roles, and Saveroom ignores those.
3. Add users to the group under its **Members** tab.

## 4. Put the client roles into the ID token and userinfo

**This is the step that is easy to miss.** Keycloak's built-in `client roles` mapper adds
`resource_access.<client_id>.roles` to the **access token only** — *Add to ID token* and
*Add to userinfo* are off by default, and Saveroom reads the ID token and the userinfo
response. Without this step the user appears to hold no roles at all and every login is
refused.

That built-in mapper lives in the realm-wide `roles` client scope, so editing it changes
every client in the realm. Add a mapper on the Saveroom client's **dedicated** scope
instead:

1. **Clients → baserow → Client scopes → `baserow-dedicated` → Add mapper → By
   configuration → User Client Role**.
2. Configure it:
   - **Name**: `baserow client roles`
   - **Client ID**: `baserow` (restricts the claim to this client's roles)
   - **Token Claim Name**: `resource_access.${client_id}.roles`
   - **Claim JSON Type**: `String`
   - **Multivalued**: On
   - **Add to ID token**: **On**
   - **Add to userinfo**: **On**
   - **Add to access token**: On (harmless; leave as it comes)

Saveroom only needs one of the two token types to carry the claim — it reads both and
takes the union — but enabling both is the most forgiving configuration.

The dedicated scope is always applied, whatever scopes the client asks for, so there is
nothing to add to the provider's `scopes` list to make this mapper fire.

> If the client has **Full scope allowed** turned off, also add the roles you defined to
> the client's **Scope** tab, or Keycloak will filter them out of the token.

### Verifying the claim

Use **Clients → baserow → Client scopes → Evaluate**, pick a user, and look at
*Generated ID token*. You should see:

```json
"resource_access": {
  "baserow": {
    "roles": ["baserow-user"]
  }
}
```

If `resource_access` is missing from the ID token, the mapper's *Add to ID token* toggle
is still off.

## 5. Configure the provider

```jsonc
BASEROW_OIDC_PROVIDERS='[
  {
    // Url-safe slug. It appears in the callback URL you registered in step 1:
    // <BASEROW_PUBLIC_URL>/api/sso/oidc/callback/rhbk/
    "name": "rhbk",

    // The label on the login button.
    "display_name": "Company SSO",

    // https://<keycloak-host>/realms/<realm>. Saveroom appends
    // /.well-known/openid-configuration to discover the rest.
    "issuer": "https://keycloak.example.com/realms/main",

    "client_id": "baserow",
    "client_secret": "the-secret",

    // --- Who may sign in, and who administers the instance. ---
    "user_roles": ["baserow-user"],
    "staff_roles": ["baserow-staff"],
    "superuser_roles": ["baserow-admins"],

    // How long a session started through Keycloak lasts before the user must sign in
    // again, which is when profile changes are applied. Default 480 (8 hours); null
    // falls back to BASEROW_REFRESH_TOKEN_LIFETIME_HOURS.
    "session_lifetime_minutes": 480,

    // Refuse users whose email Keycloak has not verified (default true). The email is
    // what links a Keycloak identity to a Saveroom account.
    "require_verified_email": true
  }
]'
```

`roles_claim` is omitted above because its default is already
`resource_access.${client_id}.roles`, with `${client_id}` replaced by this provider's
`client_id`. Override it to read realm roles (`realm_access.roles`) or a custom mapper's
claim instead. A literal dot inside a claim name is escaped as `\.`.

> `BASEROW_OIDC_PROVIDERS` is parsed and validated once, at startup. **Every change needs a
> backend restart** before it takes effect, and an invalid value stops the backend from
> starting rather than failing later at login.

## 6. Verify the integration end to end

Work through these in order, so a failure tells you which layer is wrong.

1. **The claim is in the token.** Use **Evaluate** as described in step 4. If the roles
   are missing here, nothing downstream can work.
2. **Saveroom can reach the issuer.** From the backend container:

   ```bash
   curl -fsS "https://keycloak.example.com/realms/main/.well-known/openid-configuration"
   ```

   A failure here is network, DNS or TLS trust — not configuration.
3. **A user signs in.** Log in as a test user holding `baserow-user`. They land in Saveroom
   with no workspace (or can create one, if the instance allows it).
4. **A workspace admin adds them.** In a workspace, *Settings → Members → Add members*,
   search the test user and add them. They now see the workspace.
5. **Staff is granted and revoked.** Log in as a user holding `baserow-staff`: the admin
   area is available. Remove the role, sign in again: it is gone.
6. **An unmapped user is refused.** Log in as a test user holding none of the mapped
   roles. Saveroom must redirect to `/login?error=errorNoMappedRole`, and **no account may
   exist for them afterwards**.

## How access is decided on each login

1. Saveroom verifies the callback: the `state` and PKCE verifier must match the ones it
   issued, the ID token's signature, issuer, audience, expiry and nonce must check out,
   and the userinfo `sub` must equal the ID token's. With `require_verified_email` (the
   default), a user whose `email_verified` claim is not `true` is refused with
   `errorEmailNotVerified`.
2. Saveroom reads the client roles from the ID token and the userinfo response and unions
   them.
3. If the user holds none of `user_roles`, `staff_roles` or `superuser_roles`, the login is
   refused with `errorNoMappedRole` — **before** any account is provisioned.
4. `staff_roles` / `superuser_roles` are reconciled onto the user: granted when held,
   revoked when not. Only the dimensions you configure are touched.

Workspace memberships are never changed by a login. Because all of this runs only during an
OIDC login, a local break-glass administrator who never signs in through Keycloak is never
modified.

## Day-to-day operations

Profile changes reconcile on the user's **next login**. Nothing in Keycloak reaches into a
session that is already open, but a session only lasts `session_lifetime_minutes`
(8 hours by default).

### Onboard someone

1. Add them to the `baserow-users` group in Keycloak.
2. They sign in once, which creates their account.
3. A workspace admin adds them from *Workspace settings → Members → Add members*.

### Give someone access to another workspace, or restrict it

Done entirely in Saveroom by that workspace's admins: add the member, put them in a team,
and set *No access* / *Viewer* / *Editor* / *Builder* with *Manage access* on databases and
tables. Changes apply immediately. See
[Workspace access in the app](sso-oidc.md#workspace-access-in-the-app).

### Promote or demote a global administrator

Add or remove the client role listed in `staff_roles` / `superuser_roles`. The flags are
reconciled on the next login — including revocation.

### Give a workspace an administrator

An existing workspace admin (or staff, from the admin area) changes the member's role to
`ADMIN` in the members list. Keycloak is not involved.

### Offboard someone

Remove them from the Saveroom groups in Keycloak: they can no longer sign in once their
session ends (`session_lifetime_minutes`). Their workspace memberships stay until a
workspace admin removes them.

> Removing a role does **not** end an active session early. To cut access immediately,
> disable or delete the user in Keycloak, and deactivate the account from Saveroom's admin
> area.

### Rotate the client secret

Regenerate it under **Clients → baserow → Credentials**, update `client_secret` in
`BASEROW_OIDC_PROVIDERS`, and restart the backend. Logins fail in between, so do it in a
window you can tolerate.

## Hardening

### The realm

Saveroom matches an incoming SSO identity to an existing account **by email address**. Two
consequences:

* Keep realm self-registration disabled, or make sure the email address on an account is
  authoritative (for example because users come from LDAP/AD federation). A realm where a
  stranger can self-register an arbitrary address is a realm where they can attempt to
  land on someone else's Saveroom account.
* Leave `BASEROW_ALLOW_MULTIPLE_SSO_PROVIDERS_FOR_SAME_ACCOUNT` unset. By default, an
  account created through a different authentication method cannot be taken over through
  this provider — Saveroom refuses with `errorDifferentProvider`. That env var removes the
  check instance-wide; to recover specific accounts use the `link_oidc_account` command or
  the provider's `link_existing_accounts` key (see
  [Recovering locked-out accounts](sso-oidc.md#recovering-locked-out-accounts)).

### The Saveroom instance

Set the instance's email verification setting to **no verification** (admin settings).
SSO-provisioned accounts are created with their email marked unverified, so `recommended`
or `enforced` makes Saveroom send a verification mail for an address Keycloak already owns.

Set `BASEROW_OIDC_ONLY=true` to disable password signup and refuse password login for
non-staff accounts. A staff/superuser account can still use the password form (via
"display password login" on the login page) so an outage of the IdP cannot lock you out
of your own instance. **Create that break-glass account before turning this on.**

Decide who may create workspaces in the admin settings: whoever creates a workspace becomes
its admin.

### Reduce the surface: turn off the application types you don't use

If your deployment only ever uses databases, leave the application builder, dashboards and
automations switched off rather than relying on nobody creating one. The switches are in
the admin area under **Settings → Application features**, and they are instance-wide. A
disabled type cannot be created, and its existing applications are hidden and refused; the
data is not deleted, and re-enabling restores it.

See [Turning application types off instance-wide](instance-settings.md) for what each
toggle covers and how to set it through the API.

## Troubleshooting

| Symptom | Cause |
| --- | --- |
| Every login redirects to `/login?error=errorEmailNotVerified` | Keycloak reports `email_verified: false`. Verify the users' emails, enable **Trust Email** on an LDAP/AD federation provider, or set `require_verified_email: false` if the realm's addresses are authoritative. |
| Every login redirects to `/login?error=errorAuthFlowError` after a Keycloak upgrade or client change | Check the backend log: a `state`, PKCE or `sub` mismatch means something is rewriting the callback URL or the client's PKCE method is not `S256`. |
| Every login redirects to `/login?error=errorNoMappedRole` | The client-roles mapper is not enabled on the ID token *and* userinfo, or the user holds none of `user_roles` / `staff_roles` / `superuser_roles`. Check **Evaluate** (step 4). |
| The user signs in but sees no workspace | Expected: a workspace admin must add them in Saveroom. |
| A workspace admin cannot find the user in *Add members* | The user has not signed in yet (no account exists), is deactivated, or the search has fewer than 3 characters. Ask them to sign in once first. |
| A configuration change had no effect | The provider JSON is read at startup. Restart the backend. |
| The backend refuses to start after an upgrade | The provider JSON still uses retired keys: `groups_claim` / `staff_groups` / `superuser_groups` (rename), or `workspace_mappings` / `team_mappings` / `strict_membership` (remove; see [Upgrading from workspace mappings](sso-oidc.md#upgrading-from-workspace-mappings)). |
| `errorAuthFlowError` immediately after the Keycloak redirect | The redirect URI registered on the client does not match `<BASEROW_PUBLIC_URL>/api/sso/oidc/callback/<name>/`, or the backend cannot reach the issuer. Check the backend log and step 6.2. |
| `errorDifferentProvider` on login | The email already exists under another authentication method, or the provider `name` was changed. See [Recovering locked-out accounts](sso-oidc.md#recovering-locked-out-accounts). |

## Appendix: configuring the realm declaratively

The admin console steps above are the authoritative path. This appendix reproduces the
same realm-side configuration as a JSON representation, for rebuilding a realm or keeping
it in version control.

It creates exactly three things, matching steps 1, 2 and 4:

* the confidential `baserow` client, with the redirect URI from step 1;
* the three client roles from step 2;
* the `oidc-usermodel-client-role-mapper` from step 4, emitting
  `resource_access.baserow.roles` into the ID token, the access token and userinfo.

It contains no workspace information — Keycloak has no notion of a Saveroom workspace.

Unlike the example in step 5, this block carries no `//` comments: it is pasted into
Keycloak's partial import and `kcadm.sh`, which accept strict JSON only.

> Keycloak's export format varies between versions. Treat this as a starting point:
> configure one realm through the console, then use **Realm settings → Action → Partial
> export** with clients included, and take the exported block as your source of truth.

```json
{
  "clients": [
    {
      "clientId": "baserow",
      "name": "Saveroom",
      "enabled": true,
      "protocol": "openid-connect",
      "publicClient": false,
      "standardFlowEnabled": true,
      "directAccessGrantsEnabled": false,
      "serviceAccountsEnabled": false,
      "redirectUris": [
        "https://baserow.example.com/api/sso/oidc/callback/rhbk/"
      ],
      "fullScopeAllowed": true,
      "protocolMappers": [
        {
          "name": "baserow client roles",
          "protocol": "openid-connect",
          "protocolMapper": "oidc-usermodel-client-role-mapper",
          "config": {
            "usermodel.clientRoleMapping.clientId": "baserow",
            "claim.name": "resource_access.${client_id}.roles",
            "jsonType.label": "String",
            "multivalued": "true",
            "id.token.claim": "true",
            "access.token.claim": "true",
            "userinfo.token.claim": "true"
          }
        }
      ]
    }
  ],
  "roles": {
    "client": {
      "baserow": [
        { "name": "baserow-user", "description": "May sign in to Saveroom" },
        { "name": "baserow-staff", "description": "Saveroom global staff" },
        { "name": "baserow-admins", "description": "Saveroom global superuser" }
      ]
    }
  }
}
```

Apply it to a running instance in one of three ways:

1. **Admin console** — **Realm settings → Action → Partial import**, paste the JSON, and
   choose what to do about resources that already exist.
2. **`kcadm.sh`** — authenticate, then create the client from the file:

   ```bash
   kcadm.sh config credentials \
     --server https://keycloak.example.com \
     --realm master --user admin
   kcadm.sh create clients -r main -f baserow-client.json
   ```

3. **Operator-managed realms** — wrap the realm representation in a `KeycloakRealmImport`
   resource, in the same namespace as the `Keycloak` resource it names:

   ```yaml
   apiVersion: k8s.keycloak.org/v2beta1
   kind: KeycloakRealmImport
   metadata:
     name: baserow-realm
   spec:
     keycloakCRName: <name of the Keycloak resource>
     realm:
       realm: main
       enabled: true
       clients: [] # the clients block above
       roles: {}   # the roles block above
   ```

   This path only applies to a realm the Keycloak Operator manages; for any other
   instance use one of the first two.

Groups and their role mappings can be exported the same way, but group membership is
usually owned by your directory rather than by a committed file — keep users out of the
declarative realm unless you are building a throwaway environment.
