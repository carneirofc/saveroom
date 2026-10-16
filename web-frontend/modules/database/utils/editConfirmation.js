/**
 * Indicates whether the table has protected editing enabled. When enabled, row edits
 * are staged in the `pendingRowChanges` store until the user explicitly saves them,
 * and destructive or bulk row operations must be confirmed first. This is a UI
 * safeguard only; the API never enforces it.
 */
export function isProtected(table) {
  return Boolean(table?.require_edit_confirmation)
}

/**
 * Asks the user to confirm a data change when the table has protected editing
 * enabled. Resolves `true` right away for unprotected tables.
 *
 * @param store The Vuex store.
 * @param table The table the change applies to.
 * @param options `{ title, message, confirmLabel, danger }`.
 */
export async function confirmDataChange(store, table, options) {
  if (!isProtected(table)) {
    return true
  }
  return await store.dispatch('pendingRowChanges/confirm', options)
}
