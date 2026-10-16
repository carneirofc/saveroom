import MockAdapter from 'axios-mock-adapter'
import AdminBackupService from '@baserow/modules/core/services/admin/backups'

describe('admin backup service', () => {
  let client = null
  let mock = null

  beforeEach(() => {
    client = useNuxtApp().$client
    mock = new MockAdapter(client, { onNoMatch: 'throwException' })
  })

  afterEach(() => {
    mock.restore()
  })

  test('lists workspaces for the picker', async () => {
    mock
      .onGet('/admin/workspaces/options/', { params: { page: 1, search: 'a' } })
      .reply(200, { results: [{ id: 1, value: 'Acme' }] })

    const { data } = await AdminBackupService(client).listWorkspaces(1, 'a')

    expect(data.results[0].value).toBe('Acme')
  })

  test('starts and lists backups against the admin endpoint', async () => {
    mock
      .onPost('/admin/backups/workspace/1/async/', { only_structure: false })
      .reply(202, { id: 10 })
    mock
      .onGet('/admin/backups/workspace/1/')
      .reply(200, { results: [{ resource_id: 10 }] })

    const service = AdminBackupService(client)
    const { data: job } = await service.startBackup(1, {
      only_structure: false,
    })
    const { data: list } = await service.listBackups(1)

    expect(job.id).toBe(10)
    expect(list.results).toHaveLength(1)
  })

  test('manages backup schedules against the admin endpoint', async () => {
    mock
      .onPost('/admin/backups/schedules/workspace/1/', {
        name: 'Nightly',
        cron: '0 3 * * *',
      })
      .reply(200, { id: 3, name: 'Nightly' })
    mock.onPost('/admin/backups/schedules/3/run/').reply(202, { id: 13 })
    mock.onDelete('/admin/backups/schedules/3/').reply(204)

    const service = AdminBackupService(client)
    const { data: schedule } = await service.createSchedule(1, {
      name: 'Nightly',
      cron: '0 3 * * *',
    })
    const { data: job } = await service.runSchedule(3)
    const { status } = await service.deleteSchedule(3)

    expect(schedule.id).toBe(3)
    expect(job.id).toBe(13)
    expect(status).toBe(204)
  })
})
