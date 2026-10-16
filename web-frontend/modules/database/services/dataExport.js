const BASE = '/database/data-export/schedules'

export default (client) => {
  return {
    listSchedules(workspaceId) {
      return client.get(`${BASE}/workspace/${workspaceId}/`)
    },
    createSchedule(workspaceId, values) {
      return client.post(`${BASE}/workspace/${workspaceId}/`, values)
    },
    updateSchedule(scheduleId, values) {
      return client.patch(`${BASE}/${scheduleId}/`, values)
    },
    deleteSchedule(scheduleId) {
      return client.delete(`${BASE}/${scheduleId}/`)
    },
    runSchedule(scheduleId, mode = 'auto') {
      return client.post(`${BASE}/${scheduleId}/run/`, { mode })
    },
    listRuns(scheduleId) {
      return client.get(`${BASE}/${scheduleId}/runs/`)
    },
    resetState(scheduleId) {
      return client.post(`${BASE}/${scheduleId}/reset-state/`)
    },
  }
}
