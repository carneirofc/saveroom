import MockAdapter from 'axios-mock-adapter'
import BackupService from '@baserow/modules/core/services/backup'
import DataExportService from '@baserow/modules/database/services/dataExport'

describe('backup and data export services', () => {
  let client = null
  let mock = null

  beforeEach(() => {
    client = useNuxtApp().$client
    mock = new MockAdapter(client, { onNoMatch: 'throwException' })
  })

  afterEach(() => {
    mock.restore()
  })

  test('starts a backup uploaded to a destination', async () => {
    mock
      .onPost('/backups/workspace/1/async/', {
        only_structure: false,
        destination: 'offsite',
      })
      .reply(202, { id: 10, type: 'export_applications_to_destination' })

    const { data } = await BackupService(client).startBackup(1, {
      only_structure: false,
      destination: 'offsite',
    })

    expect(data.type).toBe('export_applications_to_destination')
  })

  test('restores a local backup with only the resource id', async () => {
    mock
      .onPost('/backups/workspace/1/restore/', { resource_id: 7 })
      .reply(202, { id: 11 })

    const { data } = await BackupService(client).restoreBackup(1, 7, [])

    expect(data.id).toBe(11)
  })

  test('lists and restores remote backups', async () => {
    mock
      .onGet('/backups/destinations/off%20site/workspace/1/')
      .reply(200, { results: [{ key: 'backups/workspace=1/a.zip' }] })
    mock
      .onPost('/backups/destinations/offsite/workspace/2/restore/', {
        key: 'backups/workspace=1/a.zip',
        trust_public_key: true,
      })
      .reply(202, { id: 12 })

    const service = BackupService(client)
    const { data: listed } = await service.listRemoteBackups('off site', 1)
    const { data: job } = await service.restoreRemoteBackup('offsite', 2, {
      key: 'backups/workspace=1/a.zip',
      trust_public_key: true,
    })

    expect(listed.results).toHaveLength(1)
    expect(job.id).toBe(12)
  })

  test('manages backup schedules', async () => {
    mock.onPatch('/backups/schedules/3/', { is_active: false }).reply(200, {})
    mock.onPost('/backups/schedules/3/run/').reply(202, { id: 13 })
    mock.onDelete('/backups/schedules/3/').reply(204)

    const service = BackupService(client)
    await service.updateSchedule(3, { is_active: false })
    const { data } = await service.runSchedule(3)
    const { status } = await service.deleteSchedule(3)

    expect(data.id).toBe(13)
    expect(status).toBe(204)
  })

  test('runs a datalake export schedule and lists its runs', async () => {
    mock
      .onPost('/database/data-export/schedules/4/run/', { mode: 'full' })
      .reply(202, { schedule_id: 4, mode: 'full' })
    mock
      .onGet('/database/data-export/schedules/4/runs/')
      .reply(200, [{ id: 1, state: 'finished' }])
    mock.onPost('/database/data-export/schedules/4/reset-state/').reply(204)

    const service = DataExportService(client)
    const { data: queued } = await service.runSchedule(4, 'full')
    const { data: runs } = await service.listRuns(4)
    const { status } = await service.resetState(4)

    expect(queued.mode).toBe('full')
    expect(runs[0].state).toBe('finished')
    expect(status).toBe(204)
  })

  test('creates a datalake export schedule for a workspace', async () => {
    const values = {
      database_id: 5,
      name: 'Hourly',
      cron: '0 * * * *',
      destination: 'lake',
      table_ids: null,
    }
    mock
      .onPost('/database/data-export/schedules/workspace/1/', values)
      .reply(200, { id: 9, warnings: [] })

    const { data } = await DataExportService(client).createSchedule(1, values)

    expect(data.id).toBe(9)
  })
})
