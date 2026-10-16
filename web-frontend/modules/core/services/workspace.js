import baseService from '@baserow/modules/core/crudTable/baseService'

export default (client) => {
  return Object.assign(
    baseService(
      client,
      ({ workspaceId }) => `/workspaces/users/workspace/${workspaceId}/`,
      false
    ),
    {
      fetchAll() {
        return client.get('/workspaces/')
      },
      order(order) {
        return client.post('/workspaces/order/', {
          workspaces: order,
        })
      },
      create(values) {
        return client.post('/workspaces/', values)
      },
      update(id, values) {
        return client.patch(`/workspaces/${id}/`, values)
      },
      leave(id) {
        return client.post(`/workspaces/${id}/leave/`)
      },
      delete(id) {
        return client.delete(`/workspaces/${id}/`)
      },
      fetchAllUsers(workspaceId) {
        return client.get(`/workspaces/users/workspace/${workspaceId}/`)
      },
      searchUserCandidates(workspaceId, search) {
        return client.get(
          `/workspaces/users/workspace/${workspaceId}/candidates/`,
          { params: { search } }
        )
      },
      /**
       * @param options `teamIds` the teams the users join, `accessLevel` the
       *   workspace default access level they get (`null` to let them inherit).
       */
      addUsers(workspaceId, userIds, permissions, options = {}) {
        return client.post(`/workspaces/users/workspace/${workspaceId}/`, {
          user_ids: userIds,
          permissions,
          team_ids: options.teamIds || [],
          access_level: options.accessLevel ?? null,
        })
      },
      updateUser(workspaceUserId, values) {
        return client.patch(`/workspaces/users/${workspaceUserId}/`, values)
      },
      deleteUser(workspaceUserId) {
        return client.delete(`/workspaces/users/${workspaceUserId}/`)
      },
      createInitialWorkspace(values) {
        return client.post('/workspaces/create-initial-workspace/', values)
      },
    }
  )
}
