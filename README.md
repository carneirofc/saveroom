<p align="center"><img src="web-frontend/modules/core/static/img/logo.svg" alt="Saveroom" height="48"></p>

## Saveroom: the safe room for your tables

Saveroom is a no-code database, app builder and automation platform. It is a fork of
[Baserow](https://baserow.io) with the proprietary editions removed, and it is heading in
its own direction as a fully open source project.

Upstream Baserow is open-core: most of it is MIT licensed, but the `premium/` and
`enterprise/` directories are covered by separate licenses that require a paid
subscription for production use and forbid redistribution. This fork deletes those
directories entirely, so **everything here is MIT licensed** (documentation under
CC BY-SA 4.0) and free for commercial and private use.

* A spreadsheet database hybrid combining ease of use and powerful data organization.
* Create applications and portals, and publish them on your own domain.
* Automate repetitive workflows with automations.
* Visualize your data with dashboards.
* Headless and API first.
* Self-hosted with no storage restrictions and no license checks.
* Uses popular frameworks and tools like [Django](https://www.djangoproject.com/),
  [Vue.js](https://vuejs.org/) and [PostgreSQL](https://www.postgresql.org/).

![Database screenshot](docs/assets/screenshot.png "Database screenshot")

![Form screenshot](docs/assets/screenshot_form.png "Form view screenshot")

![Application builder](docs/assets/screenshot_application_builder.png "Application builder screenshot")

![Automations](docs/assets/screenshot_automations.png "Automations screenshot")

![Dashboard](docs/assets/screenshot_dashboard.png "Dashboard screenshot")

## What this fork removes

Deleting the paid directories removes the features they implemented. What remains is the
full MIT core: databases, grid/gallery/form views, the application builder, automations,
dashboards, integrations, webhooks, the REST API and the plugin system.

Removed with `premium/`:
Kanban, calendar and timeline views; row comments; AI fields; JSON, XML, Excel and file
exports; personal views; row coloring; survey form mode; the premium admin panel.

Removed with `enterprise/`:
role-based access control; teams; SSO/SAML; audit log; field-level permissions; secure
file serve; data sync; the code runner; the AI assistant.

The plugin system is untouched, so these can be reimplemented as third party plugins.
Anything reimplemented here must be written from scratch — the removed code is not
licensed for reuse.

In addition, this fork removes generative AI end to end — not just the premium AI
fields and enterprise AI assistant, but the underlying pgvector embeddings service, the
MCP server that let AI clients such as Claude or Cursor act on your data, and the rest of
the AI infrastructure, so there is no AI code path left in the core.

## What this fork adds

These are net-new features built from scratch under the MIT license, on top of the
stripped-down core.

### Env-configured OpenID Connect (OIDC) SSO

Enterprise SSO/SAML was deleted with `enterprise/`, but this fork reintroduces
single sign-on as a small, self-contained OIDC implementation configured entirely
through environment variables — no admin UI, no database provider rows to manage. It
works with any OpenID Connect provider (Keycloak/RHBK, Authentik, Zitadel, Entra ID,
Okta, …) and is validated at startup, so a bad configuration fails fast.

The IdP only defines **global profiles** through roles in its token — who may sign in,
who is staff and who is superuser. Everything inside a workspace is managed in the app, so
creating workspaces never needs an IdP or environment change.

* **`BASEROW_OIDC_PROVIDERS`** — a JSON list of providers: `issuer`, `client_id` /
  `client_secret`, claim overrides and the profile mappings below.
* **Profiles** — `user_roles` (may sign in), `staff_roles` and `superuser_roles`, the last
  two reconciled on every login.
* **Deny by default** — a provider that maps any role refuses (and never provisions) a
  user holding none of them.
* **`BASEROW_OIDC_ONLY`** — password signup and login off for normal users, with a
  staff **break-glass** password login so an IdP outage cannot lock you out.
* **Auto-provisioning** — SSO users are created on first login even with signups disabled.

```json
BASEROW_OIDC_PROVIDERS='[{
  "name": "rhbk",
  "display_name": "Company SSO",
  "issuer": "https://keycloak.example.com/realms/main",
  "client_id": "baserow",
  "client_secret": "change-me",
  "user_roles": ["baserow-user"],
  "staff_roles": ["baserow-staff"]
}]'
```

### In-app workspace access

Workspace admins manage who is in their workspace and what they can do:

* **Add members** — pick users who already signed in, by name or email, without an
  invitation.
* **Teams** — group members.
* **Access levels** — *No access*, *Viewer*, *Editor* or *Builder* per member or team, on
  the workspace default, a database or a table; the most specific wins. Staff can manage
  access in any workspace.

**Full guide: [Single sign-on with OpenID Connect](docs/installation/sso-oidc.md)** —
every provider key, in-app workspace access, the login decision flow, a complete
multi-provider example, Docker/Compose/Helm wiring, RHBK/Keycloak setup, error codes and
troubleshooting. A step-by-step Keycloak walkthrough lives in
[the RHBK/Keycloak guide](docs/installation/sso-rhbk-keycloak.md).

### Per-application-type admin feature flags

An instance administrator can switch whole application types off — databases, the
application builder, dashboards and automations — for everyone on the instance.

* **Four toggles** — `enable_database`, `enable_builder`, `enable_dashboard` and
  `enable_automation`, all on by default. Only global staff can change them; a
  workspace ADMIN cannot.
* **Admin UI or API** — flip them under **Admin → Settings → Application features**, or
  send `PATCH /api/settings/update/` as a staff user.
* **Refused everywhere** — a disabled type is gone from the **Create new** menu, creating
  one returns `400 ERROR_APPLICATION_TYPE_DISABLED`, and existing applications of that
  type are hidden from listings and denied on every request (including published builder
  pages and database API tokens).
* **Nothing is deleted** — the data stays in place, and enabling the type again brings
  every application back exactly as it was.
* **No redeploy** — these are database-backed settings, not environment variables, and
  take effect on the next request.

```jsonc
// PATCH /api/settings/update/  (Authorization: JWT <staff token>)
{ "enable_builder": false, "enable_dashboard": false, "enable_automation": false }
```

**Full guide: [Turning application types off instance-wide](docs/installation/instance-settings.md)** —
what each toggle blocks, the admin page and API, scripting the settings after an
install, and a worked database-only example.

## Telemetry

This fork makes no outbound calls to Baserow B.V. or anyone else. The upstream
onboarding flow shipped a pre-checked box that sent your users' email, role, company
size and country to `api.baserow.io`; that has been removed.

Error reporting and product analytics have been removed entirely. One optional
observability hook remains, and is off unless you turn it on:

| Variable | Default | Effect |
| --- | --- | --- |
| `BASEROW_ENABLE_OTEL` | unset | OpenTelemetry traces, to the endpoint you supply |

It is a FOSS client and only ever reports to the endpoint you configure.

## Run the container

This fork publishes its own all-in-one image to the GitHub Container Registry, so you do
**not** need the upstream `baserow/baserow` image (which ships the premium and enterprise
editions). The image is built straight from this repository's source, so it contains the
fork's changes — the AI removal and the OIDC SSO described above.

```bash
docker run -d \
  --name baserow \
  -e BASEROW_PUBLIC_URL=http://localhost \
  -v baserow_data:/baserow/data \
  -p 80:80 \
  -p 443:443 \
  --restart unless-stopped \
  ghcr.io/carneirofc/baserow:latest
```

Then open [http://localhost](http://localhost). Saveroom stores everything (Postgres,
Redis, uploads) inside the `baserow_data` volume.

* Set `BASEROW_PUBLIC_URL` to `https://YOUR_DOMAIN` or `http://YOUR_IP` for external
  access — it must match the address you use in the browser.
* Pin a specific release instead of `latest` with a version tag, e.g.
  `ghcr.io/carneirofc/baserow:0.16.0`. Releases up to 0.15.0 were published before
  the rename and stay at the old paths: `ghcr.io/carneirofc/baserow/baserow` for the
  all-in-one image, `ghcr.io/carneirofc/baserow/{backend,web-frontend,caddy}`, and
  `oci://ghcr.io/carneirofc/baserow/charts/baserow` for the chart. Switching an
  existing install to the new paths needs no data migration: the volumes, database
  and environment variables keep their names.
* To enable SSO, pass the `BASEROW_OIDC_PROVIDERS` (and optionally `BASEROW_OIDC_ONLY`)
  environment variables — see
  [Passing the configuration to Saveroom](docs/installation/sso-oidc.md#passing-the-configuration-to-saveroom).

Images are published automatically by the
[`build-publish-image`](.github/workflows/build-publish-image.yml) GitHub Actions
workflow whenever a `v*` version tag is pushed; the `latest` tag always points at the
most recent release. The images and the Helm chart are public on GHCR, so they pull
without `docker login`.

## Installation

This fork supports two deployment paths:

* **Simple local stack** — a single [`docker-compose.yaml`](docker-compose.yaml) that builds
  the backend and web-frontend from source with PostgreSQL, Redis and a Caddy proxy on one
  origin:

  ```bash
  cp .env.compose.example .env   # then set the secrets
  docker compose up -d --build   # http://localhost
  ```

* **Kubernetes, OpenShift or Amazon EKS** — the [Helm chart](deploy/helm/saveroom) deploys
  the backend, web-frontend and Celery workers as hardened pods. It is published to GHCR
  as an OCI artifact:

  ```bash
  helm install baserow oci://ghcr.io/carneirofc/baserow/charts/saveroom \
    -n baserow --create-namespace --set publicURL=https://baserow.example.com
  ```

  PostgreSQL and Redis are optional, toggleable subcharts; media uses S3 object storage.
  Routing works through an Ingress, an AWS ALB IngressGroup or OpenShift Routes, and the
  pods run under OpenShift's default `restricted-v2` SCC with no security-profile changes.
  On EKS, S3 access can use IRSA or Pod Identity so no AWS credentials are stored at all.
  See [Installing with Helm](docs/installation/install-with-helm.md) and
  [Installing on Amazon EKS](docs/installation/install-on-eks.md).

For a single-container deployment, the all-in-one image
`ghcr.io/carneirofc/baserow` (embedded PostgreSQL + Redis) is published by CI and
covered by the generic [Docker](docs/installation/install-with-docker.md) guide.

## Documentation

Browse the hosted docs at https://carneirofc.github.io/baserow/, or the source
[in the repository](./docs/index.md). Upstream's hosted docs at
https://baserow.io/docs/index also cover the premium and enterprise features that this
fork does not ship.

## Development environment

```bash
git clone https://github.com/carneirofc/baserow.git
cd saveroom

just dc-dev build --parallel
just dc-dev up -d
```

Visit [http://localhost:3000](http://localhost:3000) for a development build with hot
reloading. See [the development environment docs](./docs/development/development-environment.md)
for more detail.

## Meta

Baserow was created by Baserow B.V. - bram@baserow.io. This fork is not affiliated with
or endorsed by Baserow B.V. "Baserow" and the Baserow logo are trademarks of Baserow
B.V.; the MIT license covers the code, not the trademarks.

Distributed under the MIT license. See `LICENSE` for more information.

Upstream repository: https://github.com/baserow/baserow

The upstream changelog can be found [here](./changelog.md).
</content>
