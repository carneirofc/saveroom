import WorkspacesAdminService from '@baserow/modules/core/services/admin/workspaces'

// Staff-only, workspace-membership-agnostic counterpart of
// `@baserow/modules/core/services/backup`: same method names/signatures so it can
// be passed as the `service` prop to `BackupsTab`/`BackupSchedulesTab`/
// `RemoteBackupsTab`, just pointed at the `/admin/backups/...` endpoints that work
// for staff on any workspace.
export default (client) => {
  return {
    listWorkspaces(page, search) {
      return WorkspacesAdminService(client).listOptions(page, search)
    },
    listDestinations() {
      return client.get('/data-destinations/')
    },
    listBackups(workspaceId) {
      return client.get(`/admin/backups/workspace/${workspaceId}/`)
    },
    startBackup(workspaceId, values) {
      return client.post(
        `/admin/backups/workspace/${workspaceId}/async/`,
        values
      )
    },
    deleteBackup(workspaceId, resourceId) {
      return client.delete(
        `/admin/backups/workspace/${workspaceId}/${resourceId}/`
      )
    },
    restoreBackup(workspaceId, resourceId, applicationIds = null) {
      const data = { resource_id: resourceId }
      if (applicationIds && applicationIds.length > 0) {
        data.application_ids = applicationIds
      }
      return client.post(
        `/admin/backups/workspace/${workspaceId}/restore/`,
        data
      )
    },
    listSchedules(workspaceId) {
      return client.get(`/admin/backups/schedules/workspace/${workspaceId}/`)
    },
    createSchedule(workspaceId, values) {
      return client.post(
        `/admin/backups/schedules/workspace/${workspaceId}/`,
        values
      )
    },
    updateSchedule(scheduleId, values) {
      return client.patch(`/admin/backups/schedules/${scheduleId}/`, values)
    },
    deleteSchedule(scheduleId) {
      return client.delete(`/admin/backups/schedules/${scheduleId}/`)
    },
    runSchedule(scheduleId) {
      return client.post(`/admin/backups/schedules/${scheduleId}/run/`)
    },
    listRemoteBackups(destination, workspaceId) {
      return client.get(
        `/admin/backups/destinations/${encodeURIComponent(
          destination
        )}/workspace/${workspaceId}/`
      )
    },
    restoreRemoteBackup(destination, workspaceId, values) {
      return client.post(
        `/admin/backups/destinations/${encodeURIComponent(
          destination
        )}/workspace/${workspaceId}/restore/`,
        values
      )
    },
  }
}
