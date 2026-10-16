export default (client) => {
  return {
    fetchAll(workspaceId) {
      return client.get(`/api-clients/workspace/${workspaceId}/`)
    },
    create(workspaceId, values) {
      return client.post(`/api-clients/workspace/${workspaceId}/`, values)
    },
    get(clientId) {
      return client.get(`/api-clients/${clientId}/`)
    },
    update(clientId, values) {
      return client.patch(`/api-clients/${clientId}/`, values)
    },
    delete(clientId) {
      return client.delete(`/api-clients/${clientId}/`)
    },
    /**
     * The response of this call is the only time the full key is readable, the
     * backend only stores a hash of it.
     */
    createKey(clientId, values) {
      return client.post(`/api-clients/${clientId}/keys/`, values)
    },
    /**
     * Revokes rather than deletes: the key stops working but the record is kept, so
     * the response is the updated key and not an empty body.
     */
    revokeKey(keyId) {
      return client.delete(`/api-clients/keys/${keyId}/`)
    },
  }
}
