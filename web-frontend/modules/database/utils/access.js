export const ACCESS_INHERIT = 'inherit'
export const ACCESS_LEVELS = ['none', 'viewer', 'editor', 'builder']

export function subjectKey(subject) {
  return `${subject.subject_type}:${subject.subject_id}`
}

/**
 * Turns the pending level selections of the access modal into the grants payload,
 * leaving out selections equal to the saved state. `inherit` removes the grant.
 *
 * @param subjects the subjects as returned by the access endpoint.
 * @param pending an object mapping `subjectKey` to a level or `inherit`.
 */
export function buildGrantChanges(subjects, pending) {
  const changes = []
  for (const subject of subjects) {
    const key = subjectKey(subject)
    if (
      !Object.prototype.hasOwnProperty.call(pending, key) ||
      subject.is_admin
    ) {
      continue
    }
    const level = pending[key] === ACCESS_INHERIT ? null : pending[key]
    if (level !== subject.level) {
      changes.push({
        subject_type: subject.subject_type,
        subject_id: subject.subject_id,
        level,
      })
    }
  }
  return changes
}
