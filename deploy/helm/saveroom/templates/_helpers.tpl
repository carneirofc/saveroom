{{/*
Base name of every resource and of the app.kubernetes.io/name selector label.
Pinned to "baserow" rather than .Chart.Name: the chart was published as
"baserow" before the product was renamed, and selectors are immutable, so
deriving them from the new chart name would break `helm upgrade` of existing
releases and recreate their volumes.
*/}}
{{- define "baserow.name" -}}
{{- default "baserow" .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/* Fully qualified app name */}}
{{- define "baserow.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- $name := include "baserow.name" . -}}
{{- if contains $name .Release.Name -}}
{{- .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}
{{- end -}}

{{- define "baserow.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/* Common labels */}}
{{- define "baserow.labels" -}}
helm.sh/chart: {{ include "baserow.chart" . }}
{{ include "baserow.selectorLabels" . }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/part-of: saveroom
{{- end -}}

{{/* Selector labels */}}
{{- define "baserow.selectorLabels" -}}
app.kubernetes.io/name: {{ include "baserow.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{/* Per-component selector labels */}}
{{- define "baserow.componentSelectorLabels" -}}
{{ include "baserow.selectorLabels" .root }}
app.kubernetes.io/component: {{ .component }}
{{- end -}}

{{- define "baserow.serviceAccountName" -}}
{{- if .Values.serviceAccount.create -}}
{{- default (include "baserow.fullname" .) .Values.serviceAccount.name -}}
{{- else -}}
{{- default "default" .Values.serviceAccount.name -}}
{{- end -}}
{{- end -}}

{{/*
Annotations for the ServiceAccount: whatever the operator supplied, plus the EKS
IRSA role annotation when aws.irsa is enabled.
*/}}
{{- define "baserow.serviceAccountAnnotations" -}}
{{- $annotations := deepCopy (default dict .Values.serviceAccount.annotations) -}}
{{- if .Values.aws.irsa.enabled -}}
{{- $_ := set $annotations "eks.amazonaws.com/role-arn" .Values.aws.irsa.roleArn -}}
{{- end -}}
{{- if $annotations -}}
{{- toYaml $annotations -}}
{{- end -}}
{{- end -}}

{{/*
Annotations for one albGroup Ingress. Call with (dict "root" . "component" <name>).

Everything is merged into a single map before rendering, so a key supplied twice cannot
produce a duplicate YAML key. `merge` gives precedence to its first argument, so the
dedicated ingress.group.* values win over anything set in ingress.annotations - those
two keys are what join the Ingresses onto one ALB, and letting a stray annotation
override them would silently split the load balancer in two.
*/}}
{{- define "baserow.albGroupIngressAnnotations" -}}
{{- $ing := .root.Values.ingress -}}
{{- $perIngress := ternary $ing.backendAnnotations $ing.webFrontendAnnotations (eq .component "backend") -}}
{{- $order := ternary $ing.group.backendOrder $ing.group.webFrontendOrder (eq .component "backend") -}}
{{- $owned := dict "alb.ingress.kubernetes.io/group.name" $ing.group.name
                   "alb.ingress.kubernetes.io/group.order" (toString $order) -}}
{{- toYaml (merge $owned (deepCopy (default dict $perIngress)) (deepCopy (default dict $ing.annotations))) -}}
{{- end -}}

{{/*
True when the chart must inject long-lived S3 credentials. In the "irsa" and
"podIdentity" modes the AWS_* credential variables are OMITTED entirely so boto3
falls through to its default credential chain and picks up the pod's web identity
token. They must never be emitted as empty strings: the backend's
set_setting_from_env_if_present() treats a present-but-empty variable as a real
value and would set AWS_ACCESS_KEY_ID = "", breaking the credential chain.
*/}}
{{- define "baserow.objectStorage.useStaticKeys" -}}
{{- if and .Values.objectStorage.enabled (eq .Values.objectStorage.auth "staticKeys") -}}true{{- end -}}
{{- end -}}

{{/*
Fail fast on value combinations that would otherwise only break inside the cluster.
Included from NOTES.txt so it runs on every template/install/upgrade.
*/}}
{{- define "baserow.validateValues" -}}
{{- if and .Values.aws.irsa.enabled .Values.aws.podIdentity.enabled -}}
{{- fail "aws.irsa.enabled and aws.podIdentity.enabled are mutually exclusive: IRSA annotates the ServiceAccount, EKS Pod Identity associates it out-of-band. Pick one." -}}
{{- end -}}
{{- if and .Values.aws.irsa.enabled (not .Values.aws.irsa.roleArn) -}}
{{- fail "aws.irsa.enabled=true requires aws.irsa.roleArn (e.g. arn:aws:iam::123456789012:role/baserow)." -}}
{{- end -}}
{{- if and .Values.aws.irsa.enabled (not .Values.serviceAccount.create) (not .Values.serviceAccount.name) -}}
{{- fail "aws.irsa.enabled=true needs a ServiceAccount to annotate: set serviceAccount.create=true, or serviceAccount.name to a ServiceAccount you annotate yourself." -}}
{{- end -}}
{{- if and .Values.objectStorage.enabled (ne .Values.objectStorage.auth "staticKeys") (not (or .Values.aws.irsa.enabled .Values.aws.podIdentity.enabled)) -}}
{{- fail (printf "objectStorage.auth=%s requires aws.irsa.enabled=true or aws.podIdentity.enabled=true, otherwise the pods have no AWS identity at all." .Values.objectStorage.auth) -}}
{{- end -}}
{{- if and .Values.ingress.enabled (eq .Values.ingress.mode "albGroup") (not .Values.ingress.group.name) -}}
{{- fail "ingress.mode=albGroup requires ingress.group.name; it is what merges the two Ingress objects onto a single ALB." -}}
{{- end -}}
{{- end -}}

{{/*
Pod annotations shared by every app Deployment. The checksums roll the pods when the
config or the credentials change - without them a config-only `helm upgrade` updates
the ConfigMap and leaves the running pods on the old values.

The secret checksum deliberately hashes the operator-supplied credential VALUES rather
than the rendered secret.yaml. That template falls back to randAlphaNum whenever it
cannot look the live Secret up, so hashing its output would produce a different
checksum on every `helm template` - rolling every pod on each Argo CD sync and showing
permanent drift. The generated secret-key/jwt-signing-key are preserved across upgrades
anyway, so they are not a reason to restart.
*/}}
{{- define "baserow.podAnnotations" -}}
checksum/config: {{ include (print $.Template.BasePath "/configmap-env.yaml") . | sha256sum }}
{{- if or .Values.branding.faviconBase64 (include "baserow.branding.inline" .) }}
checksum/branding: {{ include (print $.Template.BasePath "/configmap-branding.yaml") . | sha256sum }}
{{- end }}
checksum/secret: {{ list .Values.secrets.existingSecret
                        .Values.secrets.secretKey
                        .Values.secrets.jwtSigningKey
                        .Values.externalDatabase.password
                        .Values.externalDatabase.existingSecret
                        .Values.externalRedis.password
                        .Values.externalRedis.existingSecret
                        .Values.objectStorage.accessKeyId
                        .Values.objectStorage.secretAccessKey
                        .Values.objectStorage.existingSecret
                        | toString | sha256sum }}
{{- with .Values.podAnnotations }}
{{ toYaml . }}
{{- end }}
{{- end -}}

{{/* Chart-managed Secret name (for SECRET_KEY, external creds, S3, etc.) */}}
{{- define "baserow.secretName" -}}
{{- if .Values.secrets.existingSecret -}}
{{- .Values.secrets.existingSecret -}}
{{- else -}}
{{- include "baserow.fullname" . -}}
{{- end -}}
{{- end -}}

{{/* Image references */}}
{{- define "baserow.image.backend" -}}
{{- $tag := default .Chart.AppVersion .Values.image.backend.tag -}}
{{- printf "%s/%s:%s" .Values.image.registry .Values.image.backend.repository $tag -}}
{{- end -}}

{{- define "baserow.image.webFrontend" -}}
{{- $tag := default .Chart.AppVersion .Values.image.webFrontend.tag -}}
{{- printf "%s/%s:%s" .Values.image.registry .Values.image.webFrontend.repository $tag -}}
{{- end -}}

{{/* ---- Database connection selection ---- */}}
{{- define "baserow.database.host" -}}
{{- if .Values.postgresql.enabled -}}
{{- printf "%s-postgresql" .Release.Name -}}
{{- else -}}
{{- required "externalDatabase.host is required when postgresql.enabled=false" .Values.externalDatabase.host -}}
{{- end -}}
{{- end -}}

{{- define "baserow.database.port" -}}
{{- if .Values.postgresql.enabled -}}5432{{- else -}}{{- .Values.externalDatabase.port | default 5432 -}}{{- end -}}
{{- end -}}

{{- define "baserow.database.user" -}}
{{- if .Values.postgresql.enabled -}}{{- .Values.postgresql.auth.username -}}{{- else -}}{{- .Values.externalDatabase.user -}}{{- end -}}
{{- end -}}

{{- define "baserow.database.name" -}}
{{- if .Values.postgresql.enabled -}}{{- .Values.postgresql.auth.database -}}{{- else -}}{{- .Values.externalDatabase.database -}}{{- end -}}
{{- end -}}

{{/* Secret holding DATABASE_PASSWORD, and its key */}}
{{- define "baserow.database.secretName" -}}
{{- if .Values.postgresql.enabled -}}
{{- printf "%s-postgresql" .Release.Name -}}
{{- else if .Values.externalDatabase.existingSecret -}}
{{- .Values.externalDatabase.existingSecret -}}
{{- else -}}
{{- include "baserow.secretName" . -}}
{{- end -}}
{{- end -}}

{{- define "baserow.database.secretKey" -}}
{{- if .Values.postgresql.enabled -}}
password
{{- else if .Values.externalDatabase.existingSecret -}}
{{- .Values.externalDatabase.existingSecretPasswordKey -}}
{{- else -}}
database-password
{{- end -}}
{{- end -}}

{{/* ---- Redis connection selection ---- */}}
{{- define "baserow.redis.host" -}}
{{- if .Values.redis.enabled -}}
{{- printf "%s-redis-master" .Release.Name -}}
{{- else -}}
{{- required "externalRedis.host is required when redis.enabled=false" .Values.externalRedis.host -}}
{{- end -}}
{{- end -}}

{{- define "baserow.redis.port" -}}
{{- if .Values.redis.enabled -}}6379{{- else -}}{{- .Values.externalRedis.port | default 6379 -}}{{- end -}}
{{- end -}}

{{- define "baserow.redis.secretName" -}}
{{- if .Values.redis.enabled -}}
{{- printf "%s-redis" .Release.Name -}}
{{- else if .Values.externalRedis.existingSecret -}}
{{- .Values.externalRedis.existingSecret -}}
{{- else -}}
{{- include "baserow.secretName" . -}}
{{- end -}}
{{- end -}}

{{- define "baserow.redis.secretKey" -}}
{{- if .Values.redis.enabled -}}
redis-password
{{- else if .Values.externalRedis.existingSecret -}}
{{- .Values.externalRedis.existingSecretPasswordKey -}}
{{- else -}}
redis-password
{{- end -}}
{{- end -}}

{{/* S3 credential secret name */}}
{{- define "baserow.s3.secretName" -}}
{{- if .Values.objectStorage.existingSecret -}}
{{- .Values.objectStorage.existingSecret -}}
{{- else -}}
{{- include "baserow.secretName" . -}}
{{- end -}}
{{- end -}}

{{/* Shared non-secret env (all app pods) */}}
{{- define "baserow.envFrom" -}}
- configMapRef:
    name: {{ include "baserow.fullname" . }}-env
{{- end -}}

{{/* Secret-backed env vars, mapping Secret keys to Baserow env names */}}
{{- define "baserow.secretEnv" -}}
- name: SECRET_KEY
  valueFrom:
    secretKeyRef:
      name: {{ include "baserow.secretName" . }}
      key: secret-key
- name: BASEROW_JWT_SIGNING_KEY
  valueFrom:
    secretKeyRef:
      name: {{ include "baserow.secretName" . }}
      key: jwt-signing-key
- name: DATABASE_PASSWORD
  valueFrom:
    secretKeyRef:
      name: {{ include "baserow.database.secretName" . }}
      key: {{ include "baserow.database.secretKey" . }}
- name: REDIS_PASSWORD
  valueFrom:
    secretKeyRef:
      name: {{ include "baserow.redis.secretName" . }}
      key: {{ include "baserow.redis.secretKey" . }}
{{- if include "baserow.objectStorage.useStaticKeys" . }}
- name: AWS_ACCESS_KEY_ID
  valueFrom:
    secretKeyRef:
      name: {{ include "baserow.s3.secretName" . }}
      key: s3-access-key-id
- name: AWS_SECRET_ACCESS_KEY
  valueFrom:
    secretKeyRef:
      name: {{ include "baserow.s3.secretName" . }}
      key: s3-secret-access-key
{{- end }}
{{- end -}}

{{/* Writable-tmpfs volumes required by readOnlyRootFilesystem */}}
{{- define "baserow.tmpVolumes" -}}
- name: tmp
  emptyDir: {}
- name: dshm
  emptyDir:
    medium: Memory
{{- end -}}

{{- define "baserow.tmpVolumeMounts" -}}
- name: tmp
  mountPath: /tmp
- name: dshm
  mountPath: /dev/shm
{{- end -}}

{{/*
Whether any inline runtime branding value is set (branding.json, theme.css or
files); see templates/configmap-branding.yaml.
*/}}
{{- define "baserow.branding.inline" -}}
{{- $b := .Values.branding -}}
{{- /* showAttribution defaults to true, so only switching it off is a change. */ -}}
{{- if or $b.appName $b.colors $b.fontFamily $b.messages $b.themeCss $b.files $b.siteUrl $b.docsUrl $b.siteTitle (not $b.showAttribution) -}}true{{- end -}}
{{- end -}}
