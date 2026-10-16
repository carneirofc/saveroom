# Install with Docker Compose

> Any questions, problems or suggestions with this guide? Ask a question in our
> [issue tracker](https://github.com/carneirofc/baserow/issues) or contribute the change yourself at
> https://github.com/carneirofc/baserow/tree/develop/docs .

The root [`docker-compose.yaml`](https://github.com/carneirofc/baserow/blob/develop/docker-compose.yaml)
runs each Saveroom service in its own container: PostgreSQL, Redis, the backend, two
Celery workers, Celery beat, the web-frontend and a Caddy reverse proxy that serves the
whole app on a single origin. It builds the backend, web-frontend and Caddy images from
the checked-out source.

If you only want a single container, use the all-in-one image instead, see
[Install with Docker](install-with-docker.md).

## Requirements

Docker with the Compose plugin (`docker compose`). See
https://docs.docker.com/engine/install/.

## Quickstart

```bash
git clone --depth=1 --branch develop https://github.com/carneirofc/baserow.git ~/saveroom
cd ~/saveroom
cp .env.compose.example .env
# Set SECRET_KEY, DATABASE_PASSWORD and REDIS_PASSWORD to your own secure values.
$EDITOR .env
docker compose up -d --build
```

Saveroom is then available at http://localhost. If `docker compose` fails with
`required variable ... is missing a value`, one of the three required variables in
`.env` is empty.

## Environment variables

`.env.compose.example` lists the variables the stack reads directly:

| Variable | Purpose |
|---|---|
| `SECRET_KEY` | Django secret key (required), e.g. `openssl rand -hex 32`. |
| `BASEROW_JWT_SIGNING_KEY` | Optional; falls back to `SECRET_KEY`. |
| `DATABASE_NAME`, `DATABASE_USER`, `DATABASE_PASSWORD` | PostgreSQL credentials (password required). |
| `REDIS_PASSWORD` | Redis password (required). |
| `BASEROW_PUBLIC_URL` | The URL users open in their browser. Defaults to `http://localhost`. |
| `WEB_FRONTEND_PORT` | Host port the Caddy proxy publishes. Defaults to `80`. |

The compose file also forwards `BASEROW_OIDC_PROVIDERS`, `BASEROW_OIDC_ONLY`
([SSO](sso-oidc.md)), `BASEROW_DATA_DESTINATIONS` ([data destinations](data-destinations.md))
and the `BASEROW_BRANDING_*` variables ([branding](branding.md)). Any other setting from
the [configuration reference](configuration.md) must be added to the `x-backend-env`
block of `docker-compose.yaml`.

Migrations run automatically on startup. Built-in templates are not shipped, so
template syncing is disabled.

## HTTPS and custom ports

The Caddy proxy listens on plain HTTP only. To serve Saveroom over HTTPS, put a
TLS-terminating proxy or load balancer in front of it and set `BASEROW_PUBLIC_URL` to the
public `https://` address:

```bash
BASEROW_PUBLIC_URL=https://saveroom.example.com docker compose up -d
```

To run on another port, set both the port and the public URL:

```bash
WEB_FRONTEND_PORT=3000 BASEROW_PUBLIC_URL=http://localhost:3000 docker compose up -d
```

> Docker publishes ports on `0.0.0.0` and bypasses ufw firewall rules. See
> https://github.com/chaifeng/ufw-docker if the host relies on ufw.

The advanced [`docker-compose.yml`](https://github.com/carneirofc/baserow/blob/develop/docker-compose.yml)
(note the extension) exposes more knobs, such as automatic Caddy HTTPS through
`BASEROW_CADDY_ADDRESSES`, `HOST_PUBLISH_IP` and `WEB_FRONTEND_SSL_PORT`. It reads its
variables from `.env.example`.

## Upgrading

1. Back up your data first (see below).
2. `docker compose down`
3. `git pull`
4. `docker compose up -d --build`
5. Follow the logs with `docker compose logs -f backend` until migrations finish.

## How to

### Run management commands

```bash
docker compose exec backend /baserow/backend/docker/docker-entrypoint.sh help
docker compose exec backend /baserow/backend/docker/docker-entrypoint.sh manage migrate
```

### View the logs

```bash
docker compose logs -f
```

### Back up the database

Read `docker compose run --rm backend manage backup_baserow --help` first, and only back up
a database no running instance is writing to.

```bash
mkdir ~/baserow_backups
# The folder must be owned by the UID:GID the container runs as (9999:9999).
sudo chown 9999:9999 ~/baserow_backups/
docker compose run --rm -v ~/baserow_backups:/baserow/backups backend backup -f /baserow/backups/baserow_backup.tar.gz
```

For scheduled backups to S3, Azure or a filesystem, see
[Data destinations and backups](data-destinations.md).

### Restore the database

Read `docker compose run --rm backend manage restore_baserow --help` first. Restore over a
direct (not pooled) database connection into a new, empty database.

```bash
docker compose run --rm -v ~/baserow_backups:/baserow/backups backend restore -f /baserow/backups/baserow_backup.tar.gz
```
