export default (client) => {
  return {
    /**
     * @param {'workspace'|'database'|'table'} scopeType
     */
    get(scopeType, scopeId) {
      return client.get(`/database/access/${scopeType}/${scopeId}/`)
    },
    /**
     * @param grants a list of `{ subject_type, subject_id, level }`, where a `null`
     *   level removes the grant so the subject inherits again.
     */
    set(scopeType, scopeId, grants) {
      return client.put(`/database/access/${scopeType}/${scopeId}/`, { grants })
    },
  }
}
