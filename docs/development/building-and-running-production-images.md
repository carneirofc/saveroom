# Building and Running Production Images

This guide covers building Saveroom's production Docker images locally and running them for testing or deployment preparation.

## Overview

Saveroom provides several image types for different deployment scenarios:

| Image | Use Case | Command |
|-------|----------|---------|
| `backend` | Backend API server (separate deployment) | `just build backend` |
| `web-frontend` | Nuxt frontend (separate deployment) | `just build web-frontend` |
| `all-in-one` | Single container with embedded PostgreSQL/Redis | `just build all-in-one` |
| `all-in-one-lite` | Single container without PostgreSQL/Redis | `just build all-in-one-lite` |

## Quick Start

### Build and Run All-in-One

The simplest way to test production images locally:

```bash
# Build the all-in-one image
just build all-in-one

# Run it
just dc-deploy all-in-one up -d

# View logs
just dc-deploy all-in-one logs -f

# Access at http://localhost
```

### Build and Run Separate Services

For testing the production multi-container setup:

```bash
# Build production images
just dc-prod build --parallel

# Run production stack
just dc-prod up -d

# View logs
just dc-prod logs -f

# Access at http://localhost:3000 (frontend) and http://localhost:8000 (API)
```

## Building Images

### The `just build` Command

Build individual deployment images:

```bash
# Build with default tag (:latest)
just build backend
just build web-frontend
just build all-in-one

# Build with custom tag
just build backend 2.0.0
just build all-in-one 2.0.0

# Build with additional Docker arguments
just build backend latest --no-cache
just build all-in-one 2.0.0 --progress=plain
```

### Available Build Targets

```bash
just build
# Shows:
#   backend         - Backend API server
#   web-frontend    - Nuxt web frontend
#   all-in-one      - Single container (production)
#   all-in-one-lite - Single container without postgres/redis
```

### Building with `dc-prod`

The `just dc-prod build` command builds production images using Docker Compose:

```bash
# Build all services
just dc-prod build --parallel

# Build specific service
just dc-prod build backend

# Build without cache
just dc-prod build --no-cache --parallel
```

`just dc-prod` pulls the published images for the given `BASEROW_VERSION`. To build the
`prod` target from source instead, use the root `docker-compose.yaml` (`docker compose up -d --build`).

### Image Tagging

| Command | Resulting Tag |
|---------|---------------|
| `just build backend` | `saveroom/backend:latest` |
| `just build backend 2.0.0` | `saveroom/backend:2.0.0` |
| `just build all-in-one` | `saveroom/all-in-one:latest` |
| `just build all-in-one 2.0.0` | `saveroom/all-in-one:2.0.0` |
| `just build all-in-one-lite` | `saveroom/all-in-one:lite-latest` |

## Running Production Images

### Using `dc-prod`

Run the full production stack (backend, frontend, celery workers, database, redis):

```bash
# Start production stack (builds if needed)
just dc-prod up -d

# View logs
just dc-prod logs -f

# Stop
just dc-prod down
```

By default, `dc-prod` builds images locally. To use pre-built images from a registry:

```bash
# Pull and run a specific version
BASEROW_VERSION=2.0.5 just dc-prod up -d

# This pulls from the registry instead of building
```

### Using `dc-deploy`

Run specific deployment configurations:

```bash
just dc-deploy
# Shows available deployments:
#   all-in-one      - All-in-one container (production)
```

#### All-in-One Container

The all-in-one image includes everything: backend, frontend, celery, PostgreSQL, and Redis.

```bash
# Build the all-in-one image
just build all-in-one

# Run it
just dc-deploy all-in-one up -d

# View logs
just dc-deploy all-in-one logs -f

# Stop
just dc-deploy all-in-one down

# Stop and remove data
just dc-deploy all-in-one down -v
```

Access at http://localhost (port 80).

#### All-in-One Lite

For when you have external PostgreSQL and Redis:

```bash
# Build
just build all-in-one-lite

# Run with external database
docker run -d \
  -e DATABASE_URL=postgres://user:pass@host:5432/baserow \
  -e REDIS_URL=redis://host:6379 \
  -e BASEROW_PUBLIC_URL=https://baserow.example.com \
  -p 80:80 \
  saveroom/all-in-one:lite-latest
```

## Environment Configuration

### Production Environment Variables

Key variables for production:

| Variable | Description | Example |
|----------|-------------|---------|
| `BASEROW_PUBLIC_URL` | Public URL for Saveroom | `https://baserow.example.com` |
| `SECRET_KEY` | Django secret key | (generate a secure random string) |
| `DATABASE_URL` | PostgreSQL connection | `postgres://user:pass@host:5432/db` |
| `REDIS_URL` | Redis connection | `redis://host:6379` |
| `EMAIL_SMTP` | Enable SMTP | `yes` |
| `EMAIL_SMTP_HOST` | SMTP server | `smtp.example.com` |
| `FROM_EMAIL` | Sender email | `noreply@example.com` |

### Using .env Files

Create a `.env` file for production settings:

```bash
# Copy example
cp .env.example .env

# Edit with your settings
vim .env

# Run with env file
docker compose --env-file .env -f docker-compose.yml up -d
```

## Image Sizes

Typical production image sizes:

| Image | Approximate Size |
|-------|------------------|
| `saveroom/backend:latest` | ~500MB |
| `saveroom/web-frontend:latest` | ~400MB |
| `saveroom/all-in-one:latest` (all-in-one) | ~1.5GB |
| `saveroom/all-in-one:lite-latest` | ~1GB |

## Dockerfile Targets

Each Dockerfile has multiple build targets:

### Backend Dockerfile

| Target | Purpose |
|--------|---------|
| `prod` | Production image (minimal, no dev deps) |
| `dev` | Development image (includes dev deps, tools) |
| `ci` | CI image (includes test deps) |

### Web-Frontend Dockerfile

| Target | Purpose |
|--------|---------|
| `prod` | Production image (built assets, production deps only) |
| `dev` | Development image (all deps, hot reload support) |
| `ci` | CI image (includes test deps) |

### All-in-One Dockerfile

| Target | Purpose |
|--------|---------|
| `prod` | Full all-in-one with PostgreSQL/Redis |
| `prod-lite` | All-in-one without PostgreSQL/Redis |
| `dev` | Development all-in-one |

## Troubleshooting

### Build Failures

```bash
# Clear Docker builder cache
# WARNING: This clears ALL Docker builder cache, not just Saveroom!
just prune

# Build without cache
just build backend latest --no-cache

# Build with verbose output
just build backend latest --progress=plain
```

### Container Won't Start

```bash
# Check logs
just dc-prod logs backend
just dc-deploy all-in-one logs

# Check container status
just dc-prod ps
docker ps -a

# Run with interactive shell to debug
docker run -it --entrypoint bash saveroom/backend:latest
```

### Database Connection Issues

```bash
# For all-in-one, check internal PostgreSQL
just dc-deploy all-in-one exec baserow_all_in_one psql -U baserow

# For separate deployment
just dc-prod exec db psql -U baserow
```

### Image Too Large

If images are unexpectedly large:

```bash
# Check image layers
docker history saveroom/backend:latest

# Inspect image
docker inspect saveroom/backend:latest

# Check what's inside
docker run --rm -it saveroom/backend:latest du -sh /*
```

## Exporting Images

To transfer images without a registry:

```bash
# Save to tar.gz
docker save saveroom/backend:latest | gzip > baserow-backend.tar.gz

# Load on another machine
docker load < baserow-backend.tar.gz
```

## Further Reading

- [install-with-docker.md](../installation/install-with-docker.md) - Production installation guide
- [running-the-dev-env-with-docker.md](running-the-dev-env-with-docker.md) - Development environment
- [justfile.md](justfile.md) - Complete command reference
