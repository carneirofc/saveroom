# Installing with Helm

The Helm chart deploys Saveroom on Kubernetes as five separate workloads — `backend`,
`web-frontend`, `celery` worker, `celery-export` worker and `celery-beat` — with optional bundled PostgreSQL
and Redis. It runs on plain Kubernetes, on OpenShift under the default `restricted-v2`
SCC, and on Amazon EKS.

For the EKS-specific deployment shape (internal ALB behind a CloudFront VPC origin,
IRSA, S3 media) see [Installing on Amazon EKS](install-on-eks.md).

- Chart source: [`deploy/helm/saveroom`](../../deploy/helm/saveroom)
- Published as: `oci://ghcr.io/carneirofc/baserow/charts/saveroom`

## Prerequisites

- Kubernetes 1.23+ and Helm 3.8+ (OCI support).
- An Ingress controller, or OpenShift Routes.
- For production: a managed PostgreSQL 18 and Redis, and S3-compatible object storage.
  The bundled subcharts are fine for evaluation but are not a database strategy.

## Install

```sh
helm install baserow oci://ghcr.io/carneirofc/baserow/charts/saveroom \
  --namespace baserow --create-namespace \
  --set publicURL=https://baserow.example.com \
  --set ingress.enabled=true \
  --set ingress.className=nginx \
  --set ingress.host=baserow.example.com
```

From a checkout, fetch the subcharts first:

```sh
helm dependency build deploy/helm/saveroom
helm install baserow deploy/helm/saveroom -n baserow --create-namespace -f my-values.yaml
```

Two ready-made presets ship with the chart; copy one and edit rather than starting
from scratch:

- [`values-openshift.yaml`](../../deploy/helm/saveroom/values-openshift.yaml)
- [`values-eks.yaml`](../../deploy/helm/saveroom/values-eks.yaml)

Pin the chart version in anything automated: `--version 0.2.0`.

## `publicURL` is not optional

`publicURL` must be the URL a browser actually reaches. The backend derives
`ALLOWED_HOSTS` and every absolute URL it generates (password reset links, file URLs,
websocket origins) from it. If it disagrees with reality you get `DisallowedHost`
errors, or a UI that loads and then fails every API call.

Set `extraAllowedHosts` (comma-separated) when the backend is also reached under other
hostnames — a load balancer health check hitting the pod by its DNS name, for example.

## Routing

Backend and web-frontend share one origin. `/api`, `/ws` and
`/static` go to the backend; everything else goes to the web-frontend. There is no
reverse-proxy pod and no CORS configuration.

### Ingress (plain Kubernetes)

```yaml
ingress:
  enabled: true
  mode: single
  className: nginx
  host: baserow.example.com
  tls:
    - hosts: [baserow.example.com]
      secretName: baserow-tls
  annotations:
    cert-manager.io/cluster-issuer: letsencrypt
```

`/ws` carries long-lived WebSockets. Most controllers need their read/send timeouts
raised from the default 60s — for ingress-nginx:

```yaml
  annotations:
    nginx.ingress.kubernetes.io/proxy-read-timeout: "3600"
    nginx.ingress.kubernetes.io/proxy-send-timeout: "3600"
```

### Ingress (AWS ALB)

`ingress.mode: albGroup` renders two Ingress objects joined onto one ALB via
`alb.ingress.kubernetes.io/group.name`. The split exists because the AWS Load Balancer
Controller resolves `healthcheck-path` per Ingress, so a single Ingress would force the
web-frontend to answer the backend's health probe. See
[Installing on Amazon EKS](install-on-eks.md).

The controller also merges Service annotations over Ingress annotations when building a
target group, so per-target settings can be applied without `albGroup`:

```yaml
ingress:
  enabled: true
  mode: single
  className: alb
service:
  backend:
    annotations:
      alb.ingress.kubernetes.io/healthcheck-path: /api/_health/
  webFrontend:
    annotations:
      alb.ingress.kubernetes.io/healthcheck-path: /
```

### OpenShift Routes

```yaml
openshift:
  route:
    enabled: true
    host: baserow.apps.mycluster.example.com
    tls:
      enabled: true
      termination: edge
      insecureEdgeTerminationPolicy: Redirect
```

Routes are off by default so the chart installs on clusters without the
`route.openshift.io` API.

## Database

| Mode | Values |
| --- | --- |
| Bundled (default) | `postgresql.enabled: true`. Bitnami subchart; the password is generated into Secret `<release>-postgresql` and read from there automatically. |
| External (recommended) | `postgresql.enabled: false` plus `externalDatabase.*`. |

```yaml
postgresql:
  enabled: false
externalDatabase:
  host: baserow.db.example.com
  port: 5432
  user: baserow
  database: baserow
  existingSecret: baserow-db          # preferred over an inline password
  existingSecretPasswordKey: password
```

`externalDatabase.url` sets a full DSN and overrides the discrete fields. Redis mirrors
all of this with `redis.enabled` and `externalRedis.*`.

Saveroom targets **PostgreSQL 18**. Point it at an older server and `pg_dump`-based
features will misbehave.

## Media storage

### Object storage (default, recommended)

Keeps the pods stateless, so `replicaCount.backend` can exceed 1.

```yaml
objectStorage:
  enabled: true
  auth: staticKeys
  bucketName: baserow-media
  endpointURL: https://s3.us-east-1.amazonaws.com   # or a MinIO endpoint
  region: us-east-1
  existingSecret: baserow-s3   # keys: s3-access-key-id, s3-secret-access-key
  defaultACL: ""
  querystringAuth: true
```

`auth` selects how the pods authenticate:

| Value | Credentials |
| --- | --- |
| `staticKeys` | `accessKeyId`/`secretAccessKey`, or `existingSecret`. Works with any S3-compatible endpoint. |
| `irsa` | EKS IAM Roles for Service Accounts; set `aws.irsa.enabled` and `aws.irsa.roleArn`. |
| `podIdentity` | EKS Pod Identity; set `aws.podIdentity.enabled`. |

In `irsa` and `podIdentity` the chart renders no AWS credential environment variables
and stores no `s3-*` secret keys at all, so boto3 falls through to its default
credential chain and picks up the projected web identity token.

**`defaultACL` matters.** It is empty by default, which means "send no ACL". Buckets
with ACLs disabled — S3 Object Ownership set to *Bucket owner enforced*, the default
for buckets created since April 2023 — reject any canned ACL with
`AccessControlListNotSupported`. Only set `defaultACL: public-read` for a bucket that
still has ACLs enabled.

Set `querystringAuth: false` when a CDN reads the bucket directly through an origin
access control, so media URLs are not signed.

### PVC fallback

```yaml
objectStorage:
  enabled: false
mediaPersistence:
  size: 50Gi
  storageClassName: gp3
  accessMode: ReadWriteMany
replicaCount:
  backend: 1
```

The backend and both Celery workers mount this claim, and the export worker is what
writes exports and backups, so it needs `ReadWriteMany`. `ReadWriteOnce` appears to work
for as long as the pods happen to land on the same node, and then fails with a Multi-Attach
error after a reschedule. Outside OpenShift nothing assigns an `fsGroup`, so add
`podSecurityContext.fsGroup: 1000` if the backend cannot write to `/baserow/media`.

**Attachments need object storage.** Exported files and backups are downloaded through
`/api/`, streamed out of the storage by the backend, so they work in this mode. User file
attachments and their thumbnails are still served from `MEDIA_URL`, and nothing in this
chart serves `/media/` — Django only serves it with `DEBUG=True`, and `/media` is not one
of the `backendPaths`. A deployment that relies on file fields therefore needs
`objectStorage.enabled: true`.

If a download reports that the file storage is unavailable, check
**Admin → Health** first: the instance runs a probe from a worker and reads it back from
the web process, so a split between the two is reported there by name.

## Secrets

Unless `secrets.existingSecret` is set, the chart creates `<release>-baserow` holding a
generated `secret-key` and `jwt-signing-key`. Both are **preserved across upgrades** —
the template reads the live Secret back before regenerating. Rotating `secret-key`
invalidates existing sessions and password-reset links.

To manage it yourself, create a Secret with `secret-key` and `jwt-signing-key` (plus
`database-password`, `redis-password` and the two `s3-*` keys where the chart would
otherwise supply them) and set `secrets.existingSecret` to its name.

## Extra configuration

Backend settings the chart does not model explicitly go through `extraEnv`, which is
rendered into the shared app ConfigMap. **The ConfigMap is not encrypted — no secrets
here.**

```yaml
extraEnv:
  BASEROW_ENABLE_SECURE_PROXY_SSL_HEADER: "true"
  BASEROW_FILE_UPLOAD_SIZE_LIMIT_MB: "512"
```

Single sign-on and RBAC are configured this way; see
[Single sign-on with OpenID Connect](sso-oidc.md#helm),
[SSO with Keycloak/RHBK](sso-rhbk-keycloak.md) and
[Configuration](configuration.md) for the full environment variable list.

### Data destinations

External storage for backups and datalake exports is declared with
`BASEROW_DATA_DESTINATIONS` in `extraEnv`. Keep its credentials out of the ConfigMap: put
them in a Secret, mount it with `extraVolumes`/`extraVolumeMounts` (added to the backend,
Celery worker, Celery export worker and Celery beat pods) and reference the files with `*_file` keys. A
`filesystem` destination mounts its PVC the same way.

```yaml
extraEnv:
  BASEROW_DATA_DESTINATIONS: |
    [{"name": "lake", "type": "s3", "bucket": "baserow-lake", "region": "eu-west-1",
      "purposes": ["datalake"],
      "access_key_id_file": "/run/secrets/lake/access-key-id",
      "secret_access_key_file": "/run/secrets/lake/secret-access-key"}]
extraVolumes:
  - name: lake-credentials
    secret:
      secretName: baserow-lake-credentials
extraVolumeMounts:
  - name: lake-credentials
    mountPath: /run/secrets/lake
    readOnly: true
```

With IRSA or Pod Identity, leave the key files out and the pod's AWS identity is used.
See [Data destinations, backups and datalake exports](data-destinations.md).

## Validation and safety nets

`values.schema.json` ships with the chart, so Helm rejects unknown keys, wrong types
and bad enum values on `lint`, `template` and `install`. The templates additionally
fail the render with an explanatory message for combinations a schema cannot express:

- `aws.irsa.enabled` without `aws.irsa.roleArn`
- `aws.irsa.enabled` together with `aws.podIdentity.enabled`
- `objectStorage.auth: irsa|podIdentity` with no AWS identity enabled
- `ingress.mode: albGroup` without `ingress.group.name`

Every pod carries `checksum/config` and `checksum/secret` annotations, so editing
`extraEnv` or a secret and running `helm upgrade` actually rolls the pods instead of
silently leaving them on the old values.

## Upgrading

```sh
helm repo update                    # or re-pull the OCI chart
helm diff upgrade baserow oci://ghcr.io/carneirofc/baserow/charts/saveroom -f my-values.yaml
helm upgrade baserow oci://ghcr.io/carneirofc/baserow/charts/saveroom -f my-values.yaml
```

`migrateOnStartup: true` (the default) runs Django migrations from the backend pod on
boot. With more than one backend replica the migration races between pods; for a
controlled rollout scale the backend to 1 for the upgrade, or run migrations out of
band and set `migrateOnStartup: false`.

Roll back with `helm rollback baserow <revision>` — but note that a rollback does not
reverse database migrations.

### Chart 0.1.x to 0.2.0

`openshift.route.enabled` now defaults to `false`. If you relied on the old default
without passing `values-openshift.yaml`, set it explicitly:

```yaml
openshift:
  route:
    enabled: true
```

Everything else is additive; existing values files keep working.

## Troubleshooting

```sh
kubectl get pods -l app.kubernetes.io/instance=baserow
kubectl logs deploy/baserow-backend
kubectl logs deploy/baserow-celery
kubectl logs deploy/baserow-celery-export
helm get values baserow
helm template baserow deploy/helm/saveroom -f my-values.yaml | less
```

| Symptom | Cause |
| --- | --- |
| `DisallowedHost` in the backend log | `publicURL` does not match the URL in use, or a proxy forwards a different `Host`. Add it to `extraAllowedHosts`. |
| UI loads, every API call fails | `publicURL` disagrees with the browser URL, or the backend paths are not routed to the backend Service. |
| Uploads fail with `AccessControlListNotSupported` | The bucket has ACLs disabled. Set `objectStorage.defaultACL: ""`. |
| Uploads fail with `AccessDenied` under IRSA | The role trust policy does not name `system:serviceaccount:<namespace>:<release>-baserow`, or the bucket policy is missing. |
| WebSockets drop about every 60s | The Ingress/load balancer idle timeout is too low for `/ws`. |
| `helm upgrade` changed config but nothing restarted | Chart older than 0.2.0; upgrade for the config checksums. |
| Backend cannot write to `/baserow/media` | PVC mode outside OpenShift; set `podSecurityContext.fsGroup`. |
| Download says the file storage is unavailable | The worker wrote the file where the backend cannot read it. Check **Admin → Health**; in PVC mode set `mediaPersistence.accessMode: ReadWriteMany`, or switch to `objectStorage`. |
| An export finishes but the download 404s | Chart older than 0.8.0, where downloads still pointed at `MEDIA_URL`. Upgrade. |
| Image attachments do not load in PVC mode | Expected: the chart does not serve `/media/`. Set `objectStorage.enabled: true`. |

## Related

- [Installing on Amazon EKS](install-on-eks.md)
- [Configuration](configuration.md)
- [SSO with Keycloak/RHBK](sso-rhbk-keycloak.md)
