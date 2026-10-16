/**
 * Mirrors `ALL_SCOPES` in `baserow.core.api_clients.scopes`, in the same order. The
 * backend rejects anything it does not know, so this list must stay in sync with it.
 */
export const API_CLIENT_SCOPES = [
  'backup.read',
  'backup.write',
  'backup.restore',
  'contents.read',
  'schedule.read',
  'schedule.write',
]

/**
 * Turns a scope into the suffix of its translation keys, e.g. `backup.read` into
 * `backupRead`, so `apiClientScopes.backupRead` names it and
 * `apiClientScopes.backupReadDescription` explains it.
 */
export const scopeTranslationKey = (scope) => {
  const [group, action] = scope.split('.')
  return `${group}${action.charAt(0).toUpperCase()}${action.slice(1)}`
}

/**
 * Returns `selected` with `scope` added or removed. The result keeps the backend's
 * order so the stored list is stable regardless of the order the boxes were ticked in.
 */
export const toggleScopeSelection = (selected, scope, on) => {
  const scopes = selected.filter((s) => s !== scope)
  if (on) {
    scopes.push(scope)
    scopes.sort(
      (a, b) => API_CLIENT_SCOPES.indexOf(a) - API_CLIENT_SCOPES.indexOf(b)
    )
  }
  return scopes
}
