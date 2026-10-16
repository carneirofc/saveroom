# syntax=docker/dockerfile:1.4
# Ubuntu 26.04 LTS base with Node installed from the official nodejs.org
# tarball. Ubuntu's own apt only carries Node 22, and this project requires 24
# (see .nvmrc and docs/installation/supported.md), so the runtime is pinned by
# SHA256 the same way su-exec is rather than trusting a third-party apt repo.
ARG NODE_BASE_IMAGE="ubuntu:26.04"
ARG UID="9999"
ARG GID="9999"

# =============================================================================
# Builder for su-exec (replaces gosu, smaller footprint)
# Pinned to v0.2 (commit 212b75144bbc) with SHA256 verification
# =============================================================================
FROM ubuntu:26.04 AS tool-builder

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

ENV SU_EXEC_VERSION=89c016e6e08749d583efdeda04b9f73e1218e253 \
    SU_EXEC_SHA256=0c90fe15804f2670037b90e72eb496579fe00d2c15765e5fe2ddec0f5afa35fa

# Ubuntu drops /usr/bin/pebble into the base layer without a dpkg package
# owning it, so apt can neither patch nor purge the CVEs vendored into it
# (CVE-2026-39821). No stage here runs it, so every ubuntu-based stage
# deletes it.
# hadolint ignore=DL3008
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && \
    apt-get install -y --no-install-recommends ca-certificates curl build-essential dos2unix tini && \
    curl -fsSL -o /usr/local/bin/su-exec.c "https://github.com/ncopa/su-exec/raw/${SU_EXEC_VERSION}/su-exec.c" && \
    echo "${SU_EXEC_SHA256}  /usr/local/bin/su-exec.c" | sha256sum -c - && \
    gcc -Wall -Werror -static -o /usr/local/bin/su-exec /usr/local/bin/su-exec.c && \
    chmod 0755 /usr/local/bin/su-exec && \
    rm -f /usr/bin/pebble && rm -rf /var/lib/pebble


# =============================================================================
# Node runtime on Ubuntu. Every stage below builds on this instead of pulling
# the Debian-based official node image.
# =============================================================================
FROM ${NODE_BASE_IMAGE} AS node-base

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

ARG TARGETARCH
# Keep NODE_VERSION, the SHA256s, NPM_VERSION and YARN_VERSION in sync with
# deploy/all-in-one/Dockerfile. npm is pinned because the release bundled with
# Node can carry vulnerable copies of its own dependencies (see deploy/AGENTS.md).
ENV NODE_VERSION=v24.21.0 \
    NODE_SHA256_amd64=fd8e59d5a511510f6a298afb548f18c7d2b1be404d8b4a27d94fbe49f56cb2d6 \
    NODE_SHA256_arm64=6ad1325edbdb5649c379b75a237147a666c95d4f9ae8d340fef2d1575d289ad2 \
    NPM_VERSION=12.2.0 \
    YARN_VERSION=1.22.22

# Ubuntu drops /usr/bin/pebble into the base layer without a dpkg package
# owning it, so apt can neither patch nor purge the CVEs vendored into it
# (CVE-2026-39821). Nothing here runs it, and every stage below builds on
# node-base, so deleting it once covers them all.
# hadolint ignore=DL3008
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && \
    apt-get upgrade -y && \
    apt-get install -y --no-install-recommends ca-certificates curl xz-utils && \
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
    node --version && npm --version && yarn --version && \
    rm -f /usr/bin/pebble && rm -rf /var/lib/pebble


# =============================================================================
# CI builder stage
# =============================================================================
FROM node-base AS builder-ci
ARG UID
ARG GID

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

ENV YARN_CACHE_FOLDER=/tmp/.yarn-cache

RUN mkdir -p /baserow/web-frontend && \
    chown -R $UID:$GID /baserow

USER $UID:$GID
WORKDIR /baserow/web-frontend

# Install dependencies (including dev)
RUN --mount=type=cache,target=$YARN_CACHE_FOLDER,uid=$UID,gid=$GID,sharing=locked \
    --mount=type=bind,source=web-frontend/package.json,target=/baserow/web-frontend/package.json \
    --mount=type=bind,source=web-frontend/yarn.lock,target=/baserow/web-frontend/yarn.lock \
    yarn install --pure-lockfile --cache-folder $YARN_CACHE_FOLDER


# =============================================================================
# Production builder stage
# =============================================================================
FROM node-base AS builder-prod
ARG UID
ARG GID

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

ENV YARN_CACHE_FOLDER=/tmp/.yarn-cache \
    NUXT_TELEMETRY_DISABLED=1 \
    NODE_OPTIONS="--max-old-space-size=4096" \
    NODE_ENV=production

RUN mkdir -p /baserow/web-frontend && \
    chown -R $UID:$GID /baserow/

# Copy source code
COPY --chown=$UID:$GID ./web-frontend /baserow/web-frontend/

# Copy all dependencies so we can build the production files
COPY --chown=$UID:$GID --from=builder-ci /baserow/web-frontend/node_modules /baserow/web-frontend/node_modules

COPY --from=tool-builder /usr/bin/dos2unix /usr/local/bin/dos2unix
RUN dos2unix /baserow/web-frontend/docker/docker-entrypoint.sh \
    && chmod a+x /baserow/web-frontend/docker/docker-entrypoint.sh \
    && chown $UID:$GID /baserow/web-frontend/docker/docker-entrypoint.sh

# Build metadata. Nuxt reads these while building, so they are baked into
# .output, which is all the prod stage ships. Empty unless the publishing
# workflow passes them.
# Declared last on purpose: the build date changes on every release run, so
# an ENV layer above the layers below would invalidate the build cache on
# every tag cut.
ARG BASEROW_BUILD_VERSION=""
ARG BASEROW_BUILD_COMMIT=""
ARG BASEROW_BUILD_DATE=""

ENV BASEROW_BUILD_VERSION=${BASEROW_BUILD_VERSION} \
    BASEROW_BUILD_COMMIT=${BASEROW_BUILD_COMMIT} \
    BASEROW_BUILD_DATE=${BASEROW_BUILD_DATE}

USER $UID:$GID
WORKDIR /baserow/web-frontend

# Build, then clean reinstall production only
RUN --mount=type=cache,target=$YARN_CACHE_FOLDER,uid=$UID,gid=$GID,sharing=locked \
    yarn run build


# =============================================================================
# Busybox helper stage for wget binary
# =============================================================================
FROM busybox:musl AS busybox-helper

# =============================================================================
# CI target - used in CI pipelines
# =============================================================================
FROM node-base AS ci
ARG UID
ARG GID

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

# Upgrade OS packages to patch CVEs in base image
RUN apt-get update && apt-get upgrade -y --no-install-recommends \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

ENV DOCKER_USER=baserow_docker_user \
    APP_ENV=test \
    BASEROW_IMAGE_TYPE="web-frontend"

RUN groupadd --system --gid $GID ${DOCKER_USER} && \
    useradd --shell /bin/bash -l -u $UID -g $GID -o -c "" -d /baserow -m ${DOCKER_USER} && \
    chmod 755 /baserow

COPY --from=tool-builder /usr/local/bin/su-exec /usr/local/bin/su-exec
COPY --from=tool-builder /usr/bin/tini /usr/bin/tini
COPY --from=busybox-helper /bin/wget /usr/local/bin/wget

RUN mkdir -p /baserow/reports /baserow/.cache /baserow/.yarn && \
    chown -R $UID:$GID /baserow

# Copy dependencies and source code
COPY --chown=$UID:$GID ./eslint.config.mjs /baserow/eslint.config.mjs
COPY --chown=$UID:$GID web-frontend /baserow/web-frontend

COPY --chown=$UID:$GID --from=builder-ci /baserow/web-frontend/node_modules /baserow/web-frontend/node_modules
COPY --chown=$UID:$GID --from=builder-prod /baserow/web-frontend/.nuxt /baserow/web-frontend/.nuxt
COPY --chown=$UID:$GID --from=builder-prod /baserow/web-frontend/.output /baserow/web-frontend/.output

# Create cache directories (after COPY so they don't get overwritten)
RUN mkdir -p /baserow/web-frontend/.cache /baserow/web-frontend/reports/coverage \
    && chown -R $UID:$GID /baserow/web-frontend/.cache /baserow/web-frontend/reports

COPY --chown=$UID:$GID tests /baserow/tests
COPY --chown=$UID:$GID deploy/plugins/*.sh /baserow/plugins/

USER $UID:$GID
WORKDIR /baserow/web-frontend

ENTRYPOINT ["/usr/bin/tini", "--", "/bin/bash", "/baserow/web-frontend/docker/docker-entrypoint.sh"]
HEALTHCHECK --interval=60s CMD wget -q -O /dev/null http://localhost:3000/_health/ || exit 1

CMD ["nuxt-prod"]


# =============================================================================
# Development target - used for local development with live reload
# =============================================================================
FROM node-base AS dev
ARG UID
ARG GID

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

# hadolint ignore=DL3008
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && \
    apt-get upgrade -y && \
    apt-get install -y --no-install-recommends \
    ca-certificates \
    python3 \
    python3-pip \
    build-essential \
    curl \
    wget \
    tmux \
    vim \
    lsof \
    procps \
    sudo

ENV DOCKER_USER=baserow_docker_user \
    BASEROW_IMAGE_TYPE="web-frontend" \
    PATH="/baserow/web-frontend/node_modules/.bin:$PATH" \
    YARN_CACHE_FOLDER=/tmp/.yarn-dev-cache

# Install rust-just for running justfiles. Keep in sync with the rust-just
# requirement in backend/pyproject.toml (and the version backend/uv.lock
# resolves) so both dev containers run the same just.
RUN pip3 install --break-system-packages --no-cache-dir rust-just==1.57.0

COPY --from=tool-builder /usr/local/bin/su-exec /usr/local/bin/su-exec
COPY --from=tool-builder /usr/bin/tini /usr/bin/tini
COPY --from=tool-builder /usr/bin/dos2unix /usr/local/bin/dos2unix

RUN getent group $GID || groupadd --system --gid $GID ${DOCKER_USER} && \
    useradd --shell /bin/bash -l -u $UID -g $GID -o -c "" -d /baserow -m ${DOCKER_USER} && \
    chmod 755 /baserow && \
    echo "${DOCKER_USER} ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/${DOCKER_USER} && \
    chmod 0440 /etc/sudoers.d/${DOCKER_USER}

RUN mkdir -p /baserow/web-frontend && \
    chown -R $UID:$GID /baserow

USER $UID:$GID
WORKDIR /baserow/web-frontend

# Configure tmux to preserve environment variables (don't start login shell)
RUN echo "set -g default-command \"\${SHELL}\"" > /baserow/.tmux.conf && \
    printf '%s\n' \
    '# Aliases' \
    'alias j="just"' \
    'alias y="yarn"' \
    '' \
    '# Show a helpful message' \
    'echo "Baserow frontend dev container"' \
    'echo "  y <cmd>  - Run yarn commands"' \
    'echo "  j        - See available commands"' \
    > /baserow/.bashrc

COPY ./eslint.config.mjs /baserow/eslint.config.mjs
COPY --chown=$UID:$GID web-frontend/docker/docker-entrypoint.sh /baserow/web-frontend/docker/docker-entrypoint.sh

RUN dos2unix /baserow/web-frontend/docker/docker-entrypoint.sh \
    && chmod a+x /baserow/web-frontend/docker/docker-entrypoint.sh

COPY --chown=$UID:$GID web-frontend/package.json /baserow/web-frontend/package.json
COPY --chown=$UID:$GID web-frontend/yarn.lock /baserow/web-frontend/yarn.lock

# Make sure these directories exist and are owned by the non-root user
RUN mkdir -p /baserow/web-frontend/.nuxt /baserow/web-frontend/.cache /baserow/web-frontend/.nuxt-storybook /baserow/web-frontend/.output

# Install dependencies (including dev)
RUN --mount=type=cache,target=$YARN_CACHE_FOLDER,uid=$UID,gid=$GID,sharing=locked \
    yarn install --pure-lockfile --cache-folder $YARN_CACHE_FOLDER

ENTRYPOINT ["/usr/bin/tini", "--", "/bin/bash", "/baserow/web-frontend/docker/docker-entrypoint.sh"]
HEALTHCHECK --interval=60s CMD wget -q -O /dev/null http://localhost:3000/_health/ || exit 1
CMD ["nuxt-dev"]


# =============================================================================
# Production target - minimal image with only runtime requirements
# =============================================================================
FROM node-base AS local
ARG UID
ARG GID

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

ENV DOCKER_USER=baserow_docker_user \
    BASEROW_IMAGE_TYPE="web-frontend" \
    NODE_ENV=production \
    YARN_CACHE_FOLDER=/tmp/.yarn-cache

COPY --from=tool-builder /usr/bin/dos2unix /usr/local/bin/dos2unix
COPY --from=tool-builder /usr/local/bin/su-exec /usr/local/bin/su-exec
COPY --from=tool-builder /usr/bin/tini /usr/bin/tini
COPY --from=busybox-helper /bin/wget /usr/local/bin/wget

# Upgrade OS packages to patch CVEs in base image
RUN apt-get update && apt-get upgrade -y --no-install-recommends \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Remove npm and yarn (not needed at runtime - the entrypoint runs node
# directly) to eliminate CVEs in their bundled deps (minimatch, glob, etc.)
RUN rm -rf /usr/local/lib/node_modules/npm /usr/local/bin/npm /usr/local/bin/npx \
    /usr/local/lib/node_modules/yarn /usr/local/bin/yarn /usr/local/bin/yarnpkg

RUN groupadd --system --gid $GID ${DOCKER_USER} && \
    useradd --shell /bin/bash -l -u $UID -g $GID -o -c "" -d /baserow -m ${DOCKER_USER} && \
    chmod 755 /baserow

USER $UID:$GID
RUN mkdir -p /baserow/web-frontend/docker

COPY --chown=$UID:$GID --from=builder-prod /baserow/web-frontend/.output /baserow/web-frontend/.output
COPY --chown=$UID:$GID ./web-frontend/env-remap.mjs /baserow/web-frontend/env-remap.mjs
COPY --chown=$UID:$GID ./web-frontend/docker/docker-entrypoint-prod.sh /baserow/web-frontend/docker/docker-entrypoint.sh
RUN chmod a+x /baserow/web-frontend/docker/docker-entrypoint.sh

# Repeated from builder-prod: the values are already baked into .output, this
# keeps them readable from `docker inspect` and lets a deployment correct them
# at runtime through env-remap.mjs without rebuilding.
# Declared last on purpose: the build date changes on every release run, so
# an ENV layer above the layers below would invalidate the build cache on
# every tag cut.
ARG BASEROW_BUILD_VERSION=""
ARG BASEROW_BUILD_COMMIT=""
ARG BASEROW_BUILD_DATE=""

ENV BASEROW_BUILD_VERSION=${BASEROW_BUILD_VERSION} \
    BASEROW_BUILD_COMMIT=${BASEROW_BUILD_COMMIT} \
    BASEROW_BUILD_DATE=${BASEROW_BUILD_DATE}

HEALTHCHECK --interval=10s CMD wget -q -O /dev/null http://localhost:3000/_health/ || exit 1

WORKDIR /baserow/web-frontend
ENTRYPOINT ["/baserow/web-frontend/docker/docker-entrypoint.sh"]


FROM local AS prod
