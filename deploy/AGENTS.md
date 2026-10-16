# deploy

## Purpose

Deployment artifacts: the all-in-one image, the Caddy proxy image and the Kubernetes/OpenShift/EKS Helm chart.

## Ownership

- `all-in-one/` — single image bundling backend, frontend, workers and supervisor.
- `helm/saveroom/` — chart published as `saveroom`, with presets `values.yaml`, `values-openshift.yaml`, `values-eks.yaml`.
- `caddy/` — reverse-proxy image for the split-services Compose stack (`ghcr.io/<owner>/<repo>/caddy`).
- `plugins/` — plugin packaging helpers. `branding-example/` — example branding directory.

The root `docker-compose*.y*ml` and `Caddyfile*` stay owned by the root.

## Local Contracts

### Images

- Every image reference points at this fork (`ghcr.io/carneirofc/baserow` and `…/baserow/{backend,web-frontend,caddy}`), including defaults in `all-in-one/Dockerfile`. Never Docker Hub `baserow/*`.
- Images build on `ubuntu:26.04` with PostgreSQL 18 and Redis from the Ubuntu archive (no third-party apt repos). The all-in-one copies the backend venv, so its `python3` must match.
- Every `ubuntu:26.04` stage deletes `/usr/bin/pebble` and `/var/lib/pebble` in its first `RUN` (unowned binary with CVEs); CI asserts it.
- Node comes from the SHA256-pinned nodejs.org tarball in `web-frontend/Dockerfile` and `all-in-one/Dockerfile`: keep `NODE_VERSION`, SHA256s, `NPM_VERSION`, `YARN_VERSION` identical. Raise `NPM_VERSION` when scans flag npm's own deps.
- Caddy is built from source in module mode in `all-in-one/Dockerfile` and `caddy/Dockerfile`: keep `GO_VERSION`, `CADDY_VERSION` and `CADDY_MODULE_UPGRADES` identical; drop an upgrade once Caddy requires it.
- `build-publish-image.yml` passes `BASEROW_BUILD_{VERSION,COMMIT,DATE}` to every app image and builds with `pull: true` (a `v*` tag republishes against fresh bases). Never forward those vars from Compose or the chart.
- Trivy gates images (`ci.yml` for caddy and web-frontend prod, `build-publish-image.yml` for all published images).
- Every database is `pgvector/pgvector:pg18` (Compose files, `ci.yml`, `justfile` test DB); bump together. An embedded PostgreSQL major bump is breaking: update `docs/runbooks/upgrade-embedded-postgres.md` and the guard in `all-in-one/supervisor/docker-postgres-setup.sh`.

### Workers

- Every stack runs two Celery workers: `celery-worker` (`celery,automation_workflow`) and the export worker (`export` queue: jobs, webhooks, search indexing, emails, backups, cleanup) — `exportworker` in supervisor, `celery-export-worker` in Compose, the `celery-export` Deployment in Helm. Without it jobs stay `pending`.

### Helm chart

- Resource names and selector labels keep the pinned base name `baserow` (`baserow.name` in `_helpers.tpl`); never derive them from `.Chart.Name` (selectors are immutable).
- Every preset must lint and render on its own; defaults stay platform-neutral (`openshift.route.enabled: false`). `values-openshift.yaml` stays restricted-SCC compatible (no fixed UIDs).
- New values go into `values.schema.json`; `postgresql`/`redis` stay `additionalProperties: true`.
- With `objectStorage.auth: irsa|podIdentity`, render no AWS key env vars or `s3-*` Secret keys at all (an empty var overrides the web identity); `baserow.objectStorage.useStaticKeys` is the gate.
- The chart serves no `/media/`; file fields need `objectStorage.enabled: true`. Never reintroduce `BASEROW_SERVE_FILES_THROUGH_BACKEND`.
- `mediaPersistence.accessMode` defaults to `ReadWriteMany` (backend and both workers mount it). `objectStorage.defaultACL` defaults to `""`.
- `ingress.mode: albGroup` renders two Ingresses joined by an ALB group so backend and frontend get separate health checks.
- Workloads carry `checksum/config` and `checksum/secret` (`baserow.podAnnotations`); `checksum/secret` hashes credential values, never the rendered Secret (it uses `randAlphaNum`). Renders must be stable.
- Backend settings the chart doesn't model go through `extraEnv` (e.g. `BASEROW_OIDC_PROVIDERS`, `BASEROW_OIDC_ONLY`, `BASEROW_DATA_DESTINATIONS`); secrets are mounted as files via `extraVolumes`/`extraVolumeMounts` (backend and Celery pods) and referenced with `*_file` keys.
- Bump `Chart.yaml` `version` on every chart change (CI enforces); keep `Chart.lock` consistent.

### Branding

- Branding reaches every stack as a directory at `BASEROW_BRANDING_DIR`: Helm `configmap-branding.yaml` (files keys flattened `/`→`__`, mounted at `/baserow/branding`, or `branding.existingClaim`), all-in-one `$DATA_DIR/branding`, Compose forwards `BASEROW_BRANDING_*`. `baserow.branding.inline` must count each truthy-default value (e.g. only `not showAttribution`).
- `BASEROW_BRANDING_APP_NAME` must also reach backend and Celery containers (chart `configmap-env.yaml`, Compose backend env).

## Work Guidance

- Validate chart edits: `helm lint --strict deploy/helm/saveroom`, then `helm template` each preset through `kubeconform -strict -ignore-missing-schemas`.
- User-facing chart docs: `docs/installation/install-with-helm.md` and `install-on-eks.md`, linked from `deploy/helm/README.md`; keep them consistent.
- Keep Compose, all-in-one and Helm env in sync with backend/frontend env contracts.

## Verification

- `publish-helm-chart.yml` (PRs touching `deploy/helm/**`, `v*` tags): version-bump gate, lint + kubeconform of all presets and option combos, IRSA and Route assertions, OCI push on tags.
- Locally: helm lint/template + kubeconform, and a `docker compose` bring-up.

## Child DOX Index

None.
