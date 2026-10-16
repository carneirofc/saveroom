export default (client) => {
  return {
    fetchAll(workspaceId) {
      return client.get(`/workspaces/teams/workspace/${workspaceId}/`)
    },
    create(workspaceId, values) {
      return client.post(`/workspaces/teams/workspace/${workspaceId}/`, values)
    },
    update(teamId, values) {
      return client.patch(`/workspaces/teams/${teamId}/`, values)
    },
    delete(teamId) {
      return client.delete(`/workspaces/teams/${teamId}/`)
    },
    addMembers(teamId, userIds) {
      return client.post(`/workspaces/teams/${teamId}/members/`, {
        user_ids: userIds,
      })
    },
    removeMembers(teamId, userIds) {
      return client.delete(`/workspaces/teams/${teamId}/members/`, {
        data: { user_ids: userIds },
      })
    },
  }
}
