# Protected editing

Protected editing is a per-table safeguard against accidental data changes in the
web interface. By default Saveroom saves every change as soon as you make it. With
protected editing enabled, changes wait for an explicit OK.

## Enabling it

Open the table's menu in the sidebar (the three dots next to the table name) and click
**Protected editing**. A check mark shows it is enabled. Anyone who can rename the
table can toggle it. Toggling is recorded in the audit log.

## What changes

- **Editing cells** in the grid or gallery view, or fields in the expanded row modal,
  no longer saves right away. A bar at the bottom of the view shows the number of
  unsaved changes with **Save** and **Discard** buttons. `Ctrl/Cmd + S` saves too.
  Saving sends all changes in a single request.
- **Creating, pasting, clearing, deleting and moving rows** ask for confirmation first.
- **Undo and redo** (`Ctrl/Cmd + Z`) ask for confirmation first.
- **Leaving the table or switching views** with unsaved changes asks whether to
  discard them. Closing or reloading the browser tab shows the browser's warning.
- Protected editing can't be disabled while the table has unsaved changes.

## Logging

Every saved change goes through the regular row actions, so it is recorded in the
staff audit log (**Admin → Audit log**). Row updates include the values before and
after the change, and deleted rows include their values.

## What it doesn't do

Protected editing is a user interface safeguard, not a permission. The REST API,
database tokens, integrations, automations and form submissions keep writing directly.
These writes are still recorded in the audit log. To restrict who can change data, use
[workspace and database access](../installation/workspace-access.md).
