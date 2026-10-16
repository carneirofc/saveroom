export default (client) => {
  return {
    listDestinations() {
      return client.get('/data-destinations/')
    },
    listBackups(workspaceId) {
      return client.get(`/backups/workspace/${workspaceId}/`)
    },
    startBackup(workspaceId, values) {
      return client.post(`/backups/workspace/${workspaceId}/async/`, values)
    },
    deleteBackup(workspaceId, resourceId) {
      return client.delete(`/backups/workspace/${workspaceId}/${resourceId}/`)
    },
    restoreBackup(workspaceId, resourceId, applicationIds = null) {
      const data = { resource_id: resourceId }
      if (applicationIds && applicationIds.length > 0) {
        data.application_ids = applicationIds
      }
      return client.post(`/backups/workspace/${workspaceId}/restore/`, data)
    },
    listSchedules(workspaceId) {
      return client.get(`/backups/schedules/workspace/${workspaceId}/`)
    },
    createSchedule(workspaceId, values) {
      return client.post(`/backups/schedules/workspace/${workspaceId}/`, values)
    },
    updateSchedule(scheduleId, values) {
      return client.patch(`/backups/schedules/${scheduleId}/`, values)
    },
    deleteSchedule(scheduleId) {
      return client.delete(`/backups/schedules/${scheduleId}/`)
    },
    runSchedule(scheduleId) {
      return client.post(`/backups/schedules/${scheduleId}/run/`)
    },
    listRemoteBackups(destination, workspaceId) {
      return client.get(
        `/backups/destinations/${encodeURIComponent(destination)}/workspace/${workspaceId}/`
      )
    },
    restoreRemoteBackup(destination, workspaceId, values) {
      return client.post(
        `/backups/destinations/${encodeURIComponent(destination)}/workspace/${workspaceId}/restore/`,
        values
      )
    },
  }
}
