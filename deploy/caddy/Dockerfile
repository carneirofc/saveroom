# syntax=docker/dockerfile:1.4
# =============================================================================
# Caddy reverse proxy for the split-services Compose stacks
# (root docker-compose.yaml and docker-compose.yml).
#
# The official caddy image is rebuilt on its own cadence and lags behind Go
# security releases (2.11.4 still ships a Go 1.26.5 stdlib, flagged for
# CVE-2026-39821 and friends). Building the same pinned Caddy release here lets
# the Go toolchain be bumped independently of upstream image rebuilds.
# GOTOOLCHAIN=local keeps the build on GO_VERSION instead of letting go.mod pull
# a different toolchain down.
#
# Caddy is built in module mode (as xcaddy does) so Go modules compiled into
# the binary can be raised past a Caddy release: CADDY_MODULE_UPGRADES lists
# the ones carrying CVE fixes Caddy has not shipped yet. Raise an entry when the
# image CVE scan flags a module in /usr/bin/caddy; drop it once CADDY_VERSION
# requires that version or newer.
#
# Keep CADDY_VERSION, GO_VERSION and CADDY_MODULE_UPGRADES in sync with
# deploy/all-in-one/Dockerfile.
# =============================================================================
ARG CADDY_VERSION=2.11.7
ARG GO_VERSION=1.27.2

FROM golang:${GO_VERSION} AS caddy_builder
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
# Runtime. Ubuntu 26.04 LTS, matching the other images in this repo. Only
# ca-certificates is needed (ACME/TLS); the Caddy binary is static.
# =============================================================================
FROM ubuntu:26.04

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

# Ubuntu drops /usr/bin/pebble into the base layer without a dpkg package
# owning it, so apt can neither patch nor purge the CVEs vendored into it
# (CVE-2026-39821). This image only runs caddy, so drop it.
# hadolint ignore=DL3008
RUN apt-get update && \
    apt-get upgrade -y && \
    DEBIAN_FRONTEND=noninteractive apt-get install --no-install-recommends -y \
    ca-certificates && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/* && \
    rm -f /usr/bin/pebble && rm -rf /var/lib/pebble

COPY --from=caddy_builder /usr/bin/caddy /usr/bin/caddy

# Same layout as the official image, so the Compose services can mount their
# Caddyfile and the caddy_config / caddy_data volumes unchanged.
ENV XDG_CONFIG_HOME=/config \
    XDG_DATA_HOME=/data
RUN mkdir -p /config/caddy /data/caddy /etc/caddy /baserow/media && \
    caddy version

EXPOSE 80 443 443/udp

CMD ["caddy", "run", "--config", "/etc/caddy/Caddyfile", "--adapter", "caddyfile"]
