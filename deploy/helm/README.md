# Saveroom Helm chart

Deploys this Saveroom fork on Kubernetes as separate, hardened pods — `backend`,
`web-frontend`, `celery` worker, `celery-export` worker and `celery-beat` — plus optional, toggleable
PostgreSQL and Redis subcharts.

The chart runs on plain Kubernetes, on OpenShift under the default `restricted-v2`
SCC, and on Amazon EKS behind an ALB. All pods are non-root with a read-only root
filesystem, dropped capabilities and unprivileged ports (8000/3000), and the chart
never sets `runAsUser`/`fsGroup`, so **no cluster security change is required** on
OpenShift.

> The all-in-one image is intentionally **not** used here: it starts as root,
> drops to a fixed UID via `su-exec`, chowns its data dir and binds `:80` — none
> of which is allowed under `restricted-v2`. The standalone `backend` and
> `web-frontend` images already satisfy the policy.

**Full documentation:**

- [Installing with Helm](../../docs/installation/install-with-helm.md) — the complete
  values reference and day-two operations.
- [Installing on Amazon EKS](../../docs/installation/install-on-eks.md) — internal ALB
  behind a CloudFront VPC origin, IRSA, S3 media.

## Quick start

```sh
# From the published chart
helm install baserow oci://ghcr.io/carneirofc/baserow/charts/saveroom \
  -n baserow --create-namespace \
  --set publicURL=https://baserow.example.com

# Or from a checkout
helm dependency build deploy/helm/saveroom
helm install baserow deploy/helm/saveroom -n baserow --create-namespace \
  --set publicURL=https://baserow.example.com
```

The stock values bring up the bundled PostgreSQL and Redis subcharts and expose
nothing externally — add an Ingress (or an OpenShift Route) and set `publicURL` to the
URL users will actually reach.

## Routing

Backend and web-frontend share one origin, so there is no reverse-proxy pod and no
CORS configuration. `/api`, `/ws` and `/static` go to the
backend; everything else goes to the web-frontend. `/media` is served from object
storage. Three ways to wire it up:

| Platform | Values |
| --- | --- |
| Plain Kubernetes | `ingress.enabled: true`, `ingress.className: nginx` (or your controller). One Ingress carries both path sets. |
| Amazon EKS | `ingress.enabled: true`, `ingress.className: alb`, `ingress.mode: albGroup`. Two Ingress objects are merged onto a single ALB so the backend and web-frontend target groups keep separate health checks. See [`baserow/values-eks.yaml`](baserow/values-eks.yaml). |
| OpenShift | `openshift.route.enabled: true`. See [`baserow/values-openshift.yaml`](baserow/values-openshift.yaml). |

`ingress.mode: albGroup` exists because the AWS Load Balancer Controller resolves
`alb.ingress.kubernetes.io/healthcheck-path` per Ingress, not per path — one Ingress
would force both target groups to share a single health endpoint. The controller also
merges *Service* annotations over Ingress annotations when building a target group, so
`service.backend.annotations` / `service.webFrontend.annotations` can set per-target
options without leaving `mode: single`.

## Database provisioning

| Mode | Values |
| --- | --- |
| Bundled (default) | `postgresql.enabled: true` — Bitnami subchart, password auto-managed in Secret `<release>-postgresql`. |
| External (recommended for prod) | `postgresql.enabled: false` + `externalDatabase.*` (or `externalDatabase.existingSecret`). |

Redis mirrors this with `redis.enabled` / `externalRedis.*`. Subcharts set
`global.compatibility.openshift.adaptSecurityContext=auto` so they too obey
`restricted-v2`; for production a managed database is still the recommended path.

## Media storage

**Object storage (default, recommended).** `objectStorage.enabled: true` with
`bucketName`, `endpointURL`, `region` and an auth mode. Pods stay stateless and scale
past one replica.

| `objectStorage.auth` | Credentials |
| --- | --- |
| `staticKeys` (default) | `accessKeyId`/`secretAccessKey`, or `existingSecret` with keys `s3-access-key-id` / `s3-secret-access-key`. Works with any S3-compatible endpoint. |
| `irsa` | EKS IAM Roles for Service Accounts. Set `aws.irsa.enabled` and `aws.irsa.roleArn`; the chart annotates the ServiceAccount. |
| `podIdentity` | EKS Pod Identity. Set `aws.podIdentity.enabled`; the association is created outside the chart. |

In the `irsa` and `podIdentity` modes the chart renders **no** AWS credential
environment variables and writes **no** `s3-*` keys into its Secret, so boto3 falls
through to its default credential chain. This is deliberate and load-bearing: the
backend treats a present-but-empty variable as a real value, so emitting
`AWS_ACCESS_KEY_ID=""` would break the credential chain rather than fall back.

Set `objectStorage.defaultACL: ""` (the default) on any bucket with ACLs disabled —
S3 Object Ownership "Bucket owner enforced", the default for buckets created since
April 2023. The backend would otherwise send `public-read` and every upload would fail
with `AccessControlListNotSupported`.

**PVC fallback.** `objectStorage.enabled: false` creates an RWO PVC mounted on backend
+ both celery workers and serves uploads through the backend. Keep `replicaCount.backend: 1` unless
your storage class supports ReadWriteMany. Outside OpenShift nothing assigns an
`fsGroup`, so set `podSecurityContext.fsGroup` if the backend cannot write to
`/baserow/media`.

## Personalization

All personalization is applied at runtime; no image rebuild is needed. See
`docs/installation/branding.md` for the full reference.

- **App name, colors, font, translations, CSS:** set `branding.appName`,
  `branding.colors` (palette/color token overrides), `branding.fontFamily`,
  `branding.messages` and `branding.themeCss`.
- **Logo, favicons, icons, fonts:** put their base64 content in
  `branding.files`, keyed by path inside the branding directory. For example,
  `img/logo.svg`, `img/favicon_32.png` or `icons/formula.svg`.
- **Favicon.ico:** `branding.faviconBase64` is also mounted over the served
  `/favicon.ico`.
- **Links and attribution:** `branding.siteUrl` retargets the attribution logo,
  `branding.docsUrl` the in-app help links, and `branding.siteTitle` their
  title text. `branding.showAttribution: false` removes the attribution logo,
  the public form "Powered by" block and the dashboard promo alert.
- **Large asset sets:** a ConfigMap holds at most about 1 MiB. Instead, set
  `branding.existingClaim` to a PersistentVolumeClaim that holds a complete
  branding directory.

The values are rendered into a ConfigMap mounted read-only at
`/baserow/branding` in the web-frontend pod. Changing them rolls the pod.

## Secrets

Unless `secrets.existingSecret` is set, the chart creates `<release>-baserow`
with a generated `secret-key` and `jwt-signing-key` (preserved across upgrades).
For an external DB/Redis without its own secret it also holds `database-password` and
`redis-password`, and in `objectStorage.auth: staticKeys` the two `s3-*` keys.

## Validation

`values.schema.json` is enforced by Helm on every `lint`, `template` and `install`, so
typos and bad enums fail before anything reaches the cluster. The chart additionally
fails the render with an explanatory message for combinations a schema cannot express —
IRSA without a role ARN, IRSA and Pod Identity together, `albGroup` without a group
name, or a non-`staticKeys` auth mode with no AWS identity configured.

Config and Secret checksums are stamped onto every pod, so a config-only
`helm upgrade` actually restarts the pods.

## Notes / limitations

- Custom builder domains (the all-in-one's on-demand-TLS feature) are not wired
  through path Routes; use the primary Route/Ingress host.
- `migrateOnStartup: true` runs migrations from the backend pod on boot. For
  strict zero-downtime upgrades, split this into a pre-upgrade Job later.
- No PodDisruptionBudget, HorizontalPodAutoscaler, per-component scheduling or
  configurable probe timings yet.
- Validate on your cluster: `helm lint --strict deploy/helm/saveroom`,
  `helm install --dry-run`, then
  `kubectl get pods -l app.kubernetes.io/instance=<release>`.
