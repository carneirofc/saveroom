# API clients

An API client is a credential for a non-human integration — a backup runner, a sync
job, a monitoring script. It acts on your behalf in one workspace, narrowed down to
the scopes you grant it.

A scope never widens what an integration can do. The client always acts as the user
who created it, so the regular permission checks still apply; the scopes only narrow
that user's access down to the endpoints the integration actually needs.

## Creating a client

Open the workspace's menu in the sidebar (the three dots next to the workspace name)
and click **API clients**, then **Create client**. Give it a name and tick the scopes
it needs:

| Scope | What it allows |
| --- | --- |
| `backup.read` | List backups and obtain their download URL. |
| `backup.write` | Start new backups and delete existing ones. |
| `backup.restore` | Restore a backup into a workspace. |
| `contents.read` | Read the full contents of a workspace or application. |
| `schedule.read` | List backup schedules. |
| `schedule.write` | Create, update, delete and manually trigger schedules. |

You only see the clients you created yourself. A new client has no keys yet, so it
cannot authenticate until you issue one.

## Issuing a key

Expand the client and click **Issue key**. A name is optional and only helps you tell
your keys apart. Leave **Expires on** empty for a key that never expires.

The full key is shown once, immediately after it is issued. Only a hash of it is
stored, so it cannot be shown again — copy it before closing the dialog. If you lose
it, revoke the key and issue a new one.

Authenticate requests with the key in an `Authorization` header:

```
Authorization: Client <the key you copied>
```

## Revoking and deactivating

- **Revoke** a single key to stop it working immediately. The record is kept and shown
  as revoked, so the revocation stays visible.
- **Deactivate** the client to stop *every* key of that client working at once,
  without deleting anything. Reactivating brings them all back.
- **Delete** the client to remove it and all of its keys permanently.

The key list shows when each key was last used, which is the quickest way to tell
whether a key is still in service before you revoke it.

## Auditing

Creating, updating and deleting clients and keys goes through the regular actions, so
it is recorded in the staff audit log (**Admin → Audit log**), as is everything the
client subsequently does.
