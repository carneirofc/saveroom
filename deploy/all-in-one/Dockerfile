ARG UID="9999"
ARG GID="9999"

ARG BACKEND_IMAGE=ghcr.io/carneirofc/baserow/backend
ARG WEBFRONTEND_IMAGE=ghcr.io/carneirofc/baserow/web-frontend
ARG CADDY_VERSION=2.11.7
ARG GO_VERSION=1.27.2
# hadolint ignore=DL3006
FROM ${BACKEND_IMAGE} AS backend_image
# hadolint ignore=DL3006
FROM ${WEBFRONTEND_IMAGE} AS web_frontend_image

# =============================================================================
# Caddy - built from source against a pinned Go toolchain
#
# The official caddy image is rebuilt on its own cadence and lags behind Go
# security releases (2.11.4 still ships a Go 1.26.5 stdlib, flagged for
# CVE-2026-39821 and friends). Building the same pinned Caddy release here lets
# the Go toolchain be bumped independently of upstream image rebuilds.
# GOTOOLCHAIN=local keeps the build on GO_VERSION instead of letting go.mod pull
# a different toolchain down. Built in module mode so CADDY_MODULE_UPGRADES can
# raise CVE-bearing Go modules past the Caddy release; see
# deploy/caddy/Dockerfile, which must stay identical.
# =============================================================================
FROM golang:${GO_VERSION} AS caddy_image
ARG CADDY_VERSION
ARG CADDY_MODULE_UPGRADES="google.golang.org/grpc@v1.84.0 golang.org/x/net@v0.60.0"
ENV CGO_ENABLED=0 \
    GOTOOLCHAIN=local
WORKDIR /src/caddy
# hadolint ignore=SC2086
RUN printf 'package main\n\nimport (\n\tcaddycmd "github.com/caddyserver/caddy/v2/cmd"\n\t_ "github.com/caddyserver/caddy/v2/modules/standard"\n)\n\nfunc main() {\n\tcaddycmd.Main()\n}\n' > main.go && \
    go mod init caddy && \
    go get "github.com/caddyserver/caddy/v2@v${CADDY_VERSION}" ${CADDY_MODULE_UPGRADES} && \
    go mod tidy && \
    go build -trimpath -o /usr/bin/caddy . && \
    caddy version

# =============================================================================
# Base - system dependencies (cached independently of source images)
#
# Ubuntu 26.04 LTS, matching backend/Dockerfile and web-frontend/Dockerfile. The
# backend venv copied in below is built against Ubuntu's python3 (3.14), so this
# stage must provide the same interpreter. PostgreSQL and its client come from
# Ubuntu itself, so the image carries no third-party apt repository.
# =============================================================================
FROM ubuntu:26.04 AS base
ARG UID
ARG GID
ARG TARGETARCH

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

ENV DOCKER_USER=baserow_docker_user \
    POSTGRES_VERSION=18 \
    BASEROW_IMAGE_TYPE="all-in-one" \
    DATA_DIR=/baserow/data \
    BASEROW_PLUGIN_DIR=/baserow/data/plugins

# Runtime dependencies
# Ubuntu drops /usr/bin/pebble into the base layer without a dpkg package
# owning it, so apt can neither patch nor purge the CVEs vendored into it
# (CVE-2026-39821). supervisor runs the services here, so drop it.
RUN apt-get update && \
    apt-get upgrade -y && \
    DEBIAN_FRONTEND=noninteractive TZ=Etc/UTC apt-get install --no-install-recommends -y \
    curl ca-certificates \
    python3 \
    python3-venv \
    supervisor \
    psmisc \
    gawk \
    postgresql-client-"${POSTGRES_VERSION}" \
    xmlsec1 \
    gettext \
    tini \
    tzdata-legacy \
    && apt-get clean && rm -rf /var/lib/apt/lists/* \
    && \
    # Setup user and group with fixed UID/GID for volume permission consistency
    getent group "$GID" || groupadd --system --gid "$GID" "${DOCKER_USER}" && \
    useradd --shell /bin/bash -l -u "$UID" -g "$GID" -o -c "" -d /baserow -m "${DOCKER_USER}" && \
    chmod 755 /baserow && \
    # Setup supervisor
    ln -sf /dev/stdout /var/log/supervisor/supervisord.log && \
    # Create data and plugin directories with correct ownership
    mkdir -p "${DATA_DIR}" "${BASEROW_PLUGIN_DIR}" && \
    chown -R "$UID:$GID" "${DATA_DIR}" "${BASEROW_PLUGIN_DIR}" && \
    rm -f /usr/bin/pebble && rm -rf /var/lib/pebble

COPY --from=caddy_image /usr/bin/caddy /usr/bin/caddy

# Node.js from the official nodejs.org tarball, verified by SHA256. This repeats
# the recipe in web-frontend/Dockerfile's node-base stage rather than copying the
# runtime out of the web-frontend image: that image's prod target deletes npm and
# yarn to shed their CVEs, but the plugin scripts in deploy/plugins/ run
# `yarn add`/`yarn remove` inside this image. Keep NODE_VERSION, the SHA256s,
# NPM_VERSION and YARN_VERSION in sync with web-frontend/Dockerfile.
#
# npm stays in this image (plugin install scripts may call it), so it is pinned
# rather than left at the version bundled with Node: the bundled npm can ship
# vulnerable copies of its own dependencies (tar, brace-expansion, ip-address),
# which the release image CVE scan fails on. Raise NPM_VERSION when that scan
# flags a package under /usr/local/lib/node_modules/npm.
ENV NODE_VERSION=v24.21.0 \
    NODE_SHA256_amd64=fd8e59d5a511510f6a298afb548f18c7d2b1be404d8b4a27d94fbe49f56cb2d6 \
    NODE_SHA256_arm64=6ad1325edbdb5649c379b75a237147a666c95d4f9ae8d340fef2d1575d289ad2 \
    NPM_VERSION=12.2.0 \
    YARN_VERSION=1.22.22

RUN DEBIAN_FRONTEND=noninteractive apt-get update && \
    apt-get install --no-install-recommends -y xz-utils && \
    case "${TARGETARCH:-amd64}" in \
    amd64) NODE_ARCH=x64; NODE_SHA256="$NODE_SHA256_amd64" ;; \
    arm64) NODE_ARCH=arm64; NODE_SHA256="$NODE_SHA256_arm64" ;; \
    *) echo "unsupported architecture: ${TARGETARCH}" >&2; exit 1 ;; \
    esac && \
    curl -fsSL -o /tmp/node.tar.xz \
    "https://nodejs.org/dist/${NODE_VERSION}/node-${NODE_VERSION}-linux-${NODE_ARCH}.tar.xz" && \
    echo "${NODE_SHA256}  /tmp/node.tar.xz" | sha256sum -c - && \
    tar -xJf /tmp/node.tar.xz -C /usr/local --strip-components=1 --no-same-owner \
    --exclude=CHANGELOG.md --exclude=LICENSE --exclude=README.md && \
    rm /tmp/node.tar.xz && \
    npm install -g "npm@${NPM_VERSION}" && \
    npm install -g "yarn@${YARN_VERSION}" && \
    npm cache clean --force && \
    apt-get clean && rm -rf /var/lib/apt/lists/* && \
    node --version && npm --version && yarn --version

# Copy su-exec from backend image (already built with pinned version + SHA256 verification)
COPY --from=backend_image /usr/local/bin/su-exec /usr/local/bin/su-exec

ENV POSTGRES_LOCATION=/etc/postgresql/${POSTGRES_VERSION}/main \
    UV_PROJECT_ENVIRONMENT=/baserow/venv \
    UV_CACHE_DIR=/tmp/baserow_uv_cache \
    UV_VERBOSE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/baserow/venv/bin:$PATH" \
    PYTHONPATH="/baserow/backend/src" \
    DJANGO_SETTINGS_MODULE='baserow.config.settings.base' \
    NODE_OPTIONS="--max-old-space-size=4096" \
    NODE_ENV=production


# =============================================================================
# Production Lite - no embedded database/cache (use external services)
# =============================================================================
FROM base AS prod-lite
ARG UID
ARG GID

# Web-frontend
COPY --chown=$UID:$GID --from=web_frontend_image /baserow/web-frontend /baserow/web-frontend

# Backend
COPY --chown=$UID:$GID --from=backend_image /baserow/backend /baserow/backend
COPY --chown=$UID:$GID --from=backend_image /baserow/venv /baserow/venv

# Configuration and startup scripts
COPY ./backend/docker/mime.types /etc/
COPY --chown=$UID:$GID Caddyfile /baserow/caddy/Caddyfile
COPY --chown=$UID:$GID deploy/all-in-one/supervisor/ /baserow/supervisor
COPY --chown=$UID:$GID deploy/all-in-one/baserow.sh /baserow.sh
COPY --chown=$UID:$GID deploy/plugins/*.sh /baserow/plugins/

# Build metadata for the backend running here. The web-frontend carries its
# own copy baked into the .output it was built with.
# Declared last on purpose: the build date changes on every release run, so
# an ENV layer above the layers below would invalidate the build cache on
# every tag cut.
ARG BASEROW_BUILD_VERSION=""
ARG BASEROW_BUILD_COMMIT=""
ARG BASEROW_BUILD_DATE=""

ENV BASEROW_BUILD_VERSION=${BASEROW_BUILD_VERSION} \
    BASEROW_BUILD_COMMIT=${BASEROW_BUILD_COMMIT} \
    BASEROW_BUILD_DATE=${BASEROW_BUILD_DATE}

HEALTHCHECK --interval=60s CMD ["/bin/bash", "/baserow/backend/docker/docker-entrypoint.sh", "backend-healthcheck"]
ENTRYPOINT ["/baserow.sh"]
CMD ["start"]
EXPOSE 80


# =============================================================================
# Production - adds embedded PostgreSQL + Redis
# =============================================================================
FROM base AS prod
ARG UID
ARG GID

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

# Install postgres + redis, both from the Ubuntu archive so no third-party apt
# repository is needed.
RUN apt-get update && \
    apt-get install --no-install-recommends -y \
    "postgresql-${POSTGRES_VERSION}" \
    "postgresql-${POSTGRES_VERSION}-pgvector" \
    redis-server \
    && apt-get clean && rm -rf /var/lib/apt/lists/* \
    && \
    # Setup redis
    usermod -a -G tty redis && \
    sed -i 's/daemonize yes/daemonize no/g' /etc/redis/redis.conf && \
    sed -i 's/daemonize no/daemonize no\nbind 127.0.0.1/g' /etc/redis/redis.conf && \
    sed -i '/^logfile/d' /etc/redis/redis.conf && \
    chown redis:redis /etc/redis/redis.conf

# Web-frontend
COPY --chown=$UID:$GID --from=web_frontend_image /baserow/web-frontend /baserow/web-frontend

# Backend
COPY --chown=$UID:$GID --from=backend_image /baserow/backend /baserow/backend
COPY --chown=$UID:$GID --from=backend_image /baserow/venv /baserow/venv

# Configuration and startup scripts
COPY ./backend/docker/mime.types /etc/
COPY --chown=$UID:$GID Caddyfile /baserow/caddy/Caddyfile
COPY --chown=$UID:$GID deploy/all-in-one/supervisor/ /baserow/supervisor
COPY --chown=$UID:$GID deploy/all-in-one/baserow.sh /baserow.sh
COPY --chown=$UID:$GID deploy/plugins/*.sh /baserow/plugins/

# Build metadata for the backend running here. The web-frontend carries its
# own copy baked into the .output it was built with.
# Declared last on purpose: the build date changes on every release run, so
# an ENV layer above the layers below would invalidate the build cache on
# every tag cut.
ARG BASEROW_BUILD_VERSION=""
ARG BASEROW_BUILD_COMMIT=""
ARG BASEROW_BUILD_DATE=""

ENV BASEROW_BUILD_VERSION=${BASEROW_BUILD_VERSION} \
    BASEROW_BUILD_COMMIT=${BASEROW_BUILD_COMMIT} \
    BASEROW_BUILD_DATE=${BASEROW_BUILD_DATE}

HEALTHCHECK --interval=60s CMD ["/bin/bash", "/baserow/backend/docker/docker-entrypoint.sh", "backend-healthcheck"]
ENTRYPOINT ["/baserow.sh"]
CMD ["start"]
EXPOSE 80
