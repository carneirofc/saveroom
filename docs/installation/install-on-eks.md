# Installing on Amazon EKS

This guide deploys Saveroom on EKS in the shape most private AWS estates want: an
**internal** Application Load Balancer that is never exposed to the internet, fronted by
**CloudFront using a VPC origin**, with media on S3 and **no long-lived AWS credentials
anywhere** — the pods assume an IAM role through IRSA.

Start from [`deploy/helm/saveroom/values-eks.yaml`](../../deploy/helm/saveroom/values-eks.yaml),
which encodes everything below. Read [Installing with Helm](install-with-helm.md) first
for the values that are not AWS-specific.

## Architecture

```
        browser
           │  HTTPS (ACM cert, your domain)
           ▼
      CloudFront distribution
           │  VPC origin (private ENI in your VPC)
           │  HTTP
           ▼
   internal ALB  (scheme: internal, target-type: ip)
           │
    ┌──────┴───────────────────────┐
    │ /api /ws                     │  everything else
    │ /static                      │
    ▼                              ▼
 backend Service :8000     web-frontend Service :3000
    │
    ├── RDS PostgreSQL 18
    ├── ElastiCache Redis
    └── S3 (media, via IRSA)
```

TLS terminates at CloudFront. The ALB has no public DNS and no certificate of its own;
only the CloudFront VPC origin ENI can reach it.

## Prerequisites

- An EKS cluster with the **AWS Load Balancer Controller** installed, and an OIDC
  provider associated with the cluster (`eksctl utils associate-iam-oidc-provider`).
- Private subnets tagged `kubernetes.io/role/internal-elb=1`.
- RDS PostgreSQL **18** and an ElastiCache Redis reachable from the node/pod subnets.
- An S3 bucket for media.
- CloudFront VPC origins are available only in commercial regions; check availability
  before committing to this shape.

## 1. S3 bucket

Create the bucket with ACLs disabled (the default) and all public access blocked.
CloudFront or signed URLs serve the objects; nothing needs to be public.

Because the bucket has ACLs disabled, the chart **must** send no canned ACL. That is the
default (`objectStorage.defaultACL: ""`). If a canned ACL is sent anyway, every upload
fails with:

```
An error occurred (AccessControlListNotSupported) when calling the PutObject operation:
The bucket does not allow ACLs
```

## 2. IAM role for the pods (IRSA)

Create a role the app pods assume through the cluster's OIDC provider.

**Permission policy** — least privilege for media:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ObjectAccess",
      "Effect": "Allow",
      "Action": ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"],
      "Resource": "arn:aws:s3:::baserow-media/*"
    },
    {
      "Sid": "BucketListing",
      "Effect": "Allow",
      "Action": ["s3:ListBucket", "s3:GetBucketLocation"],
      "Resource": "arn:aws:s3:::baserow-media"
    }
  ]
}
```

**Trust policy** — the `sub` condition must name the exact namespace and ServiceAccount
the chart creates, which is `<release>-baserow` (or just `<release>` when the release is
already named `baserow`). Check it with
`helm template ... | grep -A2 'kind: ServiceAccount'` before creating the role.

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Federated": "arn:aws:iam::<account-id>:oidc-provider/oidc.eks.<region>.amazonaws.com/id/<oidc-id>"
      },
      "Action": "sts:AssumeRoleWithWebIdentity",
      "Condition": {
        "StringEquals": {
          "oidc.eks.<region>.amazonaws.com/id/<oidc-id>:aud": "sts.amazonaws.com",
          "oidc.eks.<region>.amazonaws.com/id/<oidc-id>:sub": "system:serviceaccount:baserow:baserow"
        }
      }
    }
  ]
}
```

Or let `eksctl` build both — the chart creates the ServiceAccount itself, so use
`--role-only` and pass the ARN to Helm:

```sh
eksctl create iamserviceaccount \
  --cluster my-cluster --namespace baserow --name baserow \
  --attach-policy-arn arn:aws:iam::<account-id>:policy/baserow-media \
  --role-name baserow --role-only --approve
```

Then in values:

```yaml
aws:
  region: us-east-1
  irsa:
    enabled: true
    roleArn: arn:aws:iam::<account-id>:role/baserow
serviceAccount:
  create: true
objectStorage:
  auth: irsa
```

The chart annotates the ServiceAccount with `eks.amazonaws.com/role-arn`; the EKS pod
identity webhook then projects a web identity token into every app pod.

In `auth: irsa` the chart renders **no** `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY` and
writes **no** `s3-*` keys into its Secret. That is required, not cosmetic: the backend
treats a present-but-empty environment variable as a real value, so an empty
`AWS_ACCESS_KEY_ID` would be handed to boto3 as an actual (broken) credential instead of
falling through to the web identity token.

### EKS Pod Identity instead

Pod Identity needs no annotation — create the association against the chart's
ServiceAccount and tell the chart only to stop injecting credentials:

```yaml
aws:
  podIdentity:
    enabled: true
objectStorage:
  auth: podIdentity
```

```sh
aws eks create-pod-identity-association \
  --cluster-name my-cluster --namespace baserow \
  --service-account baserow --role-arn arn:aws:iam::<account-id>:role/baserow
```

The two modes are mutually exclusive and the chart refuses to render if both are on.

## 3. The internal ALB

```yaml
ingress:
  enabled: true
  className: alb
  mode: albGroup
  host: baserow.example.com
  group:
    name: baserow
  annotations:
    alb.ingress.kubernetes.io/scheme: internal
    alb.ingress.kubernetes.io/target-type: ip
    alb.ingress.kubernetes.io/listen-ports: '[{"HTTP": 80}]'
    alb.ingress.kubernetes.io/backend-protocol: HTTP
    alb.ingress.kubernetes.io/load-balancer-attributes: idle_timeout.timeout_seconds=4000
    alb.ingress.kubernetes.io/subnets: subnet-aaa,subnet-bbb
    alb.ingress.kubernetes.io/security-groups: sg-baserow-alb
  backendAnnotations:
    alb.ingress.kubernetes.io/healthcheck-path: /api/_health/
  webFrontendAnnotations:
    alb.ingress.kubernetes.io/healthcheck-path: /
```

Why each of these:

- **`mode: albGroup`** renders two Ingress objects sharing `group.name`, which the
  controller merges into one ALB. The controller resolves `healthcheck-path` per
  Ingress, so this is what lets the backend target group probe `/api/_health/` while the
  web-frontend probes `/`. A single Ingress would force one health endpoint on both, and
  the web-frontend does not serve `/api/_health/`.
- **`scheme: internal`** keeps the ALB off the internet. CloudFront reaches it over a
  private ENI.
- **`target-type: ip`** registers pod IPs directly, which VPC origins require.
- **`listen-ports: HTTP 80`** — CloudFront already terminated TLS. Use HTTPS with an ACM
  certificate here instead if your security posture requires encryption in transit
  inside the VPC.
- **`idle_timeout.timeout_seconds=4000`** — Saveroom's realtime collaboration rides
  long-lived WebSockets on `/ws`; the 60s ALB default would cut them constantly.

The ALB security group must allow inbound HTTP **from the CloudFront VPC origin's
security group**, and nothing else.

## 4. CloudFront with a VPC origin

Create a VPC origin pointing at the internal ALB's ARN, then a distribution using it.

- **Origin protocol:** HTTP only (matching `listen-ports` above).
- **Origin request policy:** `AllViewer`. This matters twice over — it forwards the
  `Host` header, so the backend sees your real domain and `publicURL` alone satisfies
  `ALLOWED_HOSTS`, and it forwards the `Sec-WebSocket-*` headers that `/ws` needs.
- **Cache policy:** `CachingDisabled` as the default behaviour, and for the
  `/api/*` and `/ws/*` path patterns. Use `CachingOptimized`
  only for `/static/*`. Caching an authenticated API response and serving it to another
  user is the failure mode to avoid here.
- **Allowed methods:** all of them, including `DELETE`, `PATCH`, `POST` and `PUT`.

If you do **not** forward the `Host` header, the backend receives the ALB's own DNS name
and rejects the request. In that case add it explicitly:

```yaml
extraEnv:
  BASEROW_EXTRA_ALLOWED_HOSTS: "internal-baserow-123456789.us-east-1.elb.amazonaws.com"
```

### Trusting the proxy

TLS terminates at CloudFront and the VPC origin forwards plain HTTP, so Django sees an
insecure request unless it is told to trust the forwarded protocol:

```yaml
extraEnv:
  BASEROW_ENABLE_SECURE_PROXY_SSL_HEADER: "true"
```

Without it the backend builds `http://` absolute URLs, refuses to set secure cookies,
and logins fail in ways that look like a frontend bug. Set it whenever anything in front
of the pods terminates TLS.

## 5. Managed data services

```yaml
postgresql:
  enabled: false
externalDatabase:
  host: baserow.<rds-id>.us-east-1.rds.amazonaws.com
  port: 5432
  user: baserow
  database: baserow
  existingSecret: baserow-db
  existingSecretPasswordKey: password

redis:
  enabled: false
externalRedis:
  host: baserow.<elasticache-id>.use1.cache.amazonaws.com
  port: 6379
  existingSecret: baserow-redis
  existingSecretPasswordKey: redis-password
```

Create the referenced Secrets before installing:

```sh
kubectl -n baserow create secret generic baserow-db --from-literal=password='...'
kubectl -n baserow create secret generic baserow-redis --from-literal=redis-password='...'
```

Use RDS for PostgreSQL **18** — Saveroom targets that major version. Security groups on
both services must admit the pod subnets.

## 6. Install

```sh
helm install baserow oci://ghcr.io/carneirofc/baserow/charts/saveroom \
  --namespace baserow --create-namespace \
  -f values-eks.yaml
```

With S3 media the pods are stateless, so the backend, web-frontend and celery
deployments all scale horizontally (`replicaCount` defaults to 2 each in the preset).
`celery-beat` is always a singleton.

## Verify

```sh
kubectl -n baserow get pods -l app.kubernetes.io/instance=baserow

# Two Ingress objects, one ALB address
kubectl -n baserow get ingress

# The role annotation landed on the ServiceAccount
kubectl -n baserow get sa baserow -o jsonpath='{.metadata.annotations}'

# The pod really has a web identity, and no static keys
kubectl -n baserow exec deploy/baserow-backend -- env | grep AWS_
#   expect AWS_ROLE_ARN and AWS_WEB_IDENTITY_TOKEN_FILE
#   expect NO AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY

# Health endpoint through the ALB
kubectl -n baserow run curl --rm -it --image=curlimages/curl --restart=Never -- \
  curl -sS -o /dev/null -w '%{http_code}\n' http://<alb-dns>/api/_health/
```

Then upload a file through the UI and confirm the object appears in the bucket. That is
the one step that exercises IRSA end to end.

## Troubleshooting

| Symptom | Cause |
| --- | --- |
| `AccessControlListNotSupported` on upload | The bucket has ACLs disabled. Set `objectStorage.defaultACL: ""`. |
| `AccessDenied` on upload, no static keys in the pod | The trust policy `sub` does not match `system:serviceaccount:<namespace>:<serviceAccountName>`. Compare it against the actual ServiceAccount name. |
| `NoCredentialsError` in the backend log | The pod has no projected token: the ServiceAccount annotation is missing, or the pods predate it. Restart the deployment after fixing. |
| `DisallowedHost` for the ALB DNS name | CloudFront is not forwarding the `Host` header. Use the `AllViewer` origin request policy, or list the ALB name in `BASEROW_EXTRA_ALLOWED_HOSTS`. |
| Login succeeds then immediately bounces | `BASEROW_ENABLE_SECURE_PROXY_SSL_HEADER` is not set, so Django will not set secure cookies. |
| Target group permanently unhealthy | The web-frontend target group is probing `/api/_health/`. Use `mode: albGroup` so each target group gets its own path. |
| WebSockets reconnect about every 60s | The ALB idle timeout is at its default; raise it via `load-balancer-attributes`. |
| 504 from CloudFront only | The ALB security group does not admit the VPC origin's security group. |
| Stale or cross-user API responses | A caching policy is applied to `/api/*`. Use `CachingDisabled` there. |

## Related

- [Installing with Helm](install-with-helm.md)
- [Configuration](configuration.md)
