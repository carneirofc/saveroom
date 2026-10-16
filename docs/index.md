# Saveroom documentation

Saveroom is an open-source no-code platform: spreadsheet-like databases, an application
builder, automations and dashboards on top of PostgreSQL. It is a fully MIT-licensed fork
of Baserow.

Start with **[Architecture](architecture.md)** for how the pieces fit together, then pick
the section that matches what you want to do.

## Run Saveroom

Pick one install path, then configure and operate it.

| I want to… | Read |
|---|---|
| Try it on one machine | [Docker (all-in-one image)](installation/install-with-docker.md) |
| Run one container per service with Compose | [Docker Compose](installation/install-with-docker-compose.md) |
| Run on Kubernetes or OpenShift | [Helm](installation/install-with-helm.md), [Amazon EKS](installation/install-on-eks.md) |
| Use a managed container platform | [Standalone images](installation/install-using-standalone-images.md) |
| Check versions of PostgreSQL, Redis and others | [Supported dependencies](installation/supported.md) |
| Set environment variables | [Configuration reference](installation/configuration.md) |
| Sign in through an identity provider | [OpenID Connect](installation/sso-oidc.md), [RHBK/Keycloak](installation/sso-rhbk-keycloak.md) |
| Change name, colours and logos | [Branding](installation/branding.md) |
| Control who sees what | [Workspace access](installation/workspace-access.md), [Turning application types off](installation/instance-settings.md) |
| Back up and restore | [Data destinations and backups](installation/data-destinations.md), [Back up and restore](runbooks/back-up-and-restore-baserow.md) |
| Monitor it | [Monitoring](installation/monitoring.md) |
| Fix a broken install or upgrade | [Debugging connection issues](tutorials/debugging-connection-issues.md), [Upgrade embedded PostgreSQL](runbooks/upgrade-embedded-postgres.md), [Migrate from a user tables database](runbooks/migrate-from-user-tables-database.md) |

## Use Saveroom

- [Understanding formulas](tutorials/understanding-baserow-formulas.md)
- [Prefill forms](tutorials/prefill-forms.md)
- [Protected editing](tutorials/protected-editing.md)

## Integrate through the API

- [REST API](apis/rest-api.md): resources, authentication and the generated API docs.
- [WebSocket API](apis/web-socket-api.md): realtime events.
- [API clients](tutorials/api-clients.md): scoped credentials for scripts and
  integrations.

## Develop Saveroom

1. [Set up the development environment](development/development-environment.md), either
   [locally](development/running-the-dev-env-locally.md) or
   [in Docker](development/running-the-dev-env-with-docker.md).
2. Learn the [`just` commands](development/justfile.md), the
   [code quality](development/code-quality.md) gates and how to
   [run tests](development/running-tests.md), including
   [end-to-end tests](development/e2e-testing.md).
3. Read the internals for the area you are changing: [database plugin](technical/database-plugin.md),
   [table persistence](technical/table-persistence.md),
   [permissions](technical/permissions-guide.md), [undo/redo](technical/undo-redo-guide.md),
   [WebSockets](technical/websockets.md), [formulas](technical/formula-technical-guide.md).
4. Follow the [patterns](patterns/jobs.md) for jobs, forms, emails and dates.

Architectural decisions are recorded as [ADRs](adr/001-phone-number-field-validation.md).

## Extend with plugins

Add field types, view types, filters or whole application types without forking:
start with [Plugin basics](plugins/introduction.md).
