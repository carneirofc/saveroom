# Upgrade the embedded PostgreSQL database (15 → 18)

This runbook only applies to the **all-in-one image** running its **embedded**
PostgreSQL database — that is, you did *not* pass `DATABASE_HOST` /
`POSTGRESQL_*` environment variables when starting the container. If you run an
external PostgreSQL server, nothing here applies: upgrade that server on its own
schedule. Saveroom supports PostgreSQL >= 14.

The all-in-one image's base moved to Ubuntu 26.04 LTS, which ships PostgreSQL 18.
A PostgreSQL data directory initialised by version 15 cannot be read by version
18, so the container refuses to start rather than risk your data:

```
Your PostgreSQL data directory was initialized with version 15, but this image is
running version 18.
```

The upgrade path is a logical dump with the old image and a restore into a fresh
data volume with the new one.

## Before you start

- Take a full backup first, following
  [Back-up Saveroom](back-up-and-restore-baserow.md). The steps below create a new
  volume and leave the old one untouched, but a separate backup is still the
  safety net if something goes wrong halfway.
- Note the exact image tag you are currently running (`docker inspect baserow`)
  — you need it to start the old PostgreSQL 15 cluster one last time.
- Budget downtime proportional to your database size; the dump and restore are
  both single-threaded.

Below, `OLD_TAG` is the version you run today (PostgreSQL 15) and `NEW_TAG` is the
version you are upgrading to (PostgreSQL 18).

## 1. Stop Saveroom

```bash
docker stop baserow
```

Confirm nothing else is still attached to the data volume with `docker ps`.

## 2. Dump the database with the old image

The old image still contains the PostgreSQL 15 server, so it can start the
existing cluster and dump it. Write the dump to your host, outside both volumes:

```bash
docker run -it --rm \
  -v baserow_data:/baserow/data \
  -v "$PWD":/baserow/host \
  ghcr.io/carneirofc/baserow:OLD_TAG \
  backend-cmd-with-db backup -f /baserow/host/pg15-backup.tar.gz
```

Check that `pg15-backup.tar.gz` exists in the current directory and is not
zero-length before continuing.

## 3. Create a fresh data volume

Do **not** delete the old volume. Keep it until the upgrade is verified — it is
your rollback.

```bash
docker volume create baserow_data_pg18
```

## 4. Restore into the new image

The new image initialises an empty PostgreSQL 18 cluster in the new volume and
restores the dump into it:

```bash
docker run -it --rm \
  -v baserow_data_pg18:/baserow/data \
  -v "$PWD":/baserow/host \
  ghcr.io/carneirofc/baserow:NEW_TAG \
  backend-cmd-with-db restore -f /baserow/host/pg15-backup.tar.gz
```

## 5. Start Saveroom on the new volume

Use your normal run command, with the volume swapped:

```bash
docker run -d \
  --name baserow \
  -v baserow_data_pg18:/baserow/data \
  # ... the rest of your usual arguments
  ghcr.io/carneirofc/baserow:NEW_TAG
```

Watch the startup logs (`docker logs -f baserow`). The PostgreSQL version guard
should no longer fire, and migrations should run to completion.

## 6. Verify, then clean up

Log in and confirm your workspaces, tables and row counts look right. Only once
you are satisfied:

```bash
docker volume rm baserow_data          # the old PostgreSQL 15 volume
rm pg15-backup.tar.gz
```

## Rollback

If anything goes wrong, the old volume is unchanged. Start your previous image
tag against it again:

```bash
docker run -d --name baserow -v baserow_data:/baserow/data \
  # ... the rest of your usual arguments
  ghcr.io/carneirofc/baserow:OLD_TAG
```

Then open an issue at https://github.com/carneirofc/baserow/issues with the
container logs from the failed attempt.
