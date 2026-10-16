import MockAdapter from 'axios-mock-adapter'
import moment from '@baserow/modules/core/moment'
import { flushPromises } from '@vue/test-utils'
import { mountSuspended } from '@nuxt/test-utils/runtime'
import BackupScheduleForm from '@baserow/modules/core/components/backups/BackupScheduleForm'
import RemoteBackupsTab from '@baserow/modules/core/components/backups/RemoteBackupsTab'
import BackupsTab from '@baserow/modules/core/components/backups/BackupsTab'
import BackupSchedulesTab from '@baserow/modules/core/components/backups/BackupSchedulesTab'
import BackupsModal from '@baserow/modules/core/components/backups/BackupsModal'
import BackupDestinationsCard from '@baserow/modules/core/components/admin/backups/BackupDestinationsCard'
import ConfirmModal from '@baserow/modules/core/components/modals/ConfirmModal'
import { restoredApplicationsFinished } from '@baserow/modules/core/utils/backups'
import DataExportScheduleForm from '@baserow/modules/database/components/dataExport/DataExportScheduleForm'
import DataExportModal from '@baserow/modules/database/components/dataExport/DataExportModal'

const BACKUP = {
  id: 4,
  resource_id: 'r4',
  created_on: '2026-01-01T03:00:00+00:00',
  exported_file_name: 'backup.zip',
  download_url: '/download/backup.zip',
  destination: '',
}

function deferred() {
  let resolve
  const promise = new Promise((done) => {
    resolve = done
  })
  return { promise, resolve }
}

// A request that never settles, so starting a restore does not go on to poll a job.
function pending() {
  return new Promise(() => {})
}

function remoteBackup(key) {
  return {
    key,
    created_on: '2026-01-01T03:00:00+00:00',
    size: 2048,
    only_structure: false,
    instance_id: 'this-instance',
    schedule_id: null,
    applications: [{ id: 5, name: key, type: 'database' }],
  }
}

describe('backups and datalake export UI', () => {
  let mock = null
  let wrapper = null
  let originalUser = null

  const setUser = (user) => {
    useNuxtApp().$store.state.auth.user = user
  }

  beforeEach(() => {
    originalUser = useNuxtApp().$store.state.auth.user
    mock = new MockAdapter(useNuxtApp().$client, {
      onNoMatch: 'throwException',
    })
  })

  afterEach(() => {
    useNuxtApp().$store.state.auth.user = originalUser
    if (wrapper) {
      wrapper.unmount()
      wrapper = null
    }
    mock.restore()
  })

  test('the backup schedule form emits normalized values', async () => {
    wrapper = await mountSuspended(BackupScheduleForm, {
      props: { destinations: [{ name: 'offsite', type: 's3' }] },
    })

    wrapper.vm.submit()
    expect(wrapper.emitted('submit')).toBeUndefined()

    wrapper.vm.values.name = '  Nightly  '
    wrapper.vm.values.destination = 'offsite'
    wrapper.vm.values.keep_last = '7'
    wrapper.vm.values.keep_days = ''
    wrapper.vm.submit()

    expect(wrapper.emitted('submit')[0][0]).toEqual({
      name: 'Nightly',
      cron: '0 3 * * *',
      timezone: 'UTC',
      destination: 'offsite',
      keep_last: 7,
      keep_days: null,
      only_structure: false,
      is_active: true,
      // Null rather than absent, so editing a scoped schedule back to the whole
      // workspace clears its previous selection.
      application_ids: null,
    })
  })

  test('the backup schedule form scopes to the selected applications', async () => {
    wrapper = await mountSuspended(BackupScheduleForm, {
      props: {
        destinations: [{ name: 'offsite', type: 's3' }],
        schedule: {
          name: 'Nightly',
          cron: '0 3 * * *',
          application_ids: [5, 9],
        },
      },
    })

    // An existing schedule that already names applications opens with the scope
    // enabled and those applications selected.
    expect(wrapper.vm.onlySelectedApplications).toBe(true)
    expect(wrapper.vm.selectedApplicationIds).toEqual([5, 9])

    wrapper.vm.submit()
    expect(wrapper.emitted('submit')[0][0].application_ids).toEqual([5, 9])

    wrapper.vm.onlySelectedApplications = false
    wrapper.vm.submit()
    expect(wrapper.emitted('submit')[1][0].application_ids).toBeNull()
  })

  test('the datalake export form requires tables when not exporting all', async () => {
    wrapper = await mountSuspended(DataExportScheduleForm, {
      props: {
        database: {
          id: 1,
          name: 'Sales',
          tables: [
            { id: 10, name: 'Orders' },
            { id: 11, name: 'Customers' },
          ],
        },
        destinations: [{ name: 'lake', type: 's3' }],
      },
    })

    wrapper.vm.values.name = 'Hourly'
    wrapper.vm.allTables = false
    wrapper.vm.submit()
    expect(wrapper.emitted('submit')).toBeUndefined()

    wrapper.vm.tableSelection[11] = true
    wrapper.vm.submit()

    const values = wrapper.emitted('submit')[0][0]
    expect(values.destination).toBe('lake')
    expect(values.table_ids).toEqual([11])
    expect(values.full_every_n).toBe(24)
    expect(values.column_naming).toBe('field_id')
  })

  test('the external storage tab lists backups of the destination', async () => {
    mock.onGet('/backups/destinations/offsite/workspace/1/').reply(200, {
      results: [
        {
          key: 'backups/workspace=1/20260101T030000Z_abc.zip',
          created_on: '2026-01-01T03:00:00+00:00',
          size: 2048,
          sha256: 'x',
          only_structure: false,
          instance_id: 'other-instance',
          baserow_version: '0.7.0',
          schedule_id: 3,
          workspace: { id: 1, name: 'Acme' },
          applications: [{ id: 5, name: 'Sales', type: 'database' }],
        },
      ],
    })

    wrapper = await mountSuspended(RemoteBackupsTab, {
      props: {
        workspace: { id: 1, name: 'Acme' },
        destinations: [
          { name: 'offsite', type: 'azure', purposes: ['backup'] },
        ],
      },
    })
    await flushPromises()

    // Translations are not loaded in unit tests, so only assert on the data itself.
    expect(wrapper.text()).toContain(
      moment('2026-01-01T03:00:00+00:00').format('L LT')
    )
    expect(wrapper.text()).toContain('Sales')
    expect(wrapper.text()).toContain('2 rowEditFieldFile.sizes.1')
  })

  test('the backup schedule form rejects invalid retention instead of keeping all', async () => {
    wrapper = await mountSuspended(BackupScheduleForm, {
      props: { destinations: [{ name: 'offsite', type: 's3' }] },
    })
    wrapper.vm.values.name = 'Nightly'

    for (const invalid of ['0', '-3', '1.5', 'abc', 0, -1]) {
      wrapper.vm.values.keep_last = invalid
      wrapper.vm.submit()
      expect(wrapper.emitted('submit')).toBeUndefined()
    }
    wrapper.vm.values.keep_last = ''
    wrapper.vm.values.keep_days = '0'
    wrapper.vm.submit()
    expect(wrapper.emitted('submit')).toBeUndefined()
    await wrapper.vm.$nextTick()
    expect(wrapper.text()).toContain('backupsModal.retentionInvalid')

    wrapper.vm.values.keep_days = 30
    wrapper.vm.submit()
    const values = wrapper.emitted('submit')[0][0]
    expect(values.keep_last).toBeNull()
    expect(values.keep_days).toBe(30)
  })

  test('the backup schedule form requires replacing a removed destination', async () => {
    wrapper = await mountSuspended(BackupScheduleForm, {
      props: {
        destinations: [{ name: 'offsite', type: 's3' }],
        schedule: { name: 'Nightly', cron: '0 3 * * *', destination: 'gone' },
      },
    })

    // The stale name stays visible rather than rendering a blank dropdown.
    expect(wrapper.vm.destinationUnavailable).toBe(true)
    expect(wrapper.text()).toContain('backupsModal.unavailableDestinationError')
    wrapper.vm.submit()
    expect(wrapper.emitted('submit')).toBeUndefined()

    // Keeping the backups on the instance is a valid choice.
    wrapper.vm.values.destination = ''
    wrapper.vm.submit()
    expect(wrapper.emitted('submit')[0][0].destination).toBe('')
  })

  test('the datalake export form validates full exports like the backend', async () => {
    wrapper = await mountSuspended(DataExportScheduleForm, {
      props: {
        database: { id: 1, name: 'Sales', tables: [] },
        destinations: [{ name: 'lake', type: 's3' }],
      },
    })
    wrapper.vm.values.name = 'Hourly'

    for (const invalid of ['', '-1', '2.5', 'abc', -1]) {
      wrapper.vm.values.full_every_n = invalid
      wrapper.vm.submit()
      expect(wrapper.emitted('submit')).toBeUndefined()
    }

    // Zero is allowed: it only exports fully when required.
    wrapper.vm.values.full_every_n = '0'
    wrapper.vm.submit()
    expect(wrapper.emitted('submit')[0][0].full_every_n).toBe(0)
  })

  test('the datalake export form requires replacing a removed storage', async () => {
    wrapper = await mountSuspended(DataExportScheduleForm, {
      props: {
        database: { id: 1, name: 'Sales', tables: [] },
        destinations: [{ name: 'lake', type: 's3' }],
        schedule: { name: 'Hourly', cron: '0 * * * *', destination: 'gone' },
      },
    })

    wrapper.vm.submit()
    expect(wrapper.emitted('submit')).toBeUndefined()
    wrapper.vm.values.destination = 'lake'
    wrapper.vm.submit()
    expect(wrapper.emitted('submit')[0][0].destination).toBe('lake')
  })

  test('deleting and restoring a backup waits for confirmation', async () => {
    const service = {
      listBackups: vi.fn().mockResolvedValue({ data: { results: [BACKUP] } }),
      deleteBackup: vi.fn().mockResolvedValue({}),
      restoreBackup: vi.fn(pending),
    }
    wrapper = await mountSuspended(BackupsTab, {
      props: {
        workspace: { id: 1, name: 'Acme' },
        destinations: [],
        service: () => service,
      },
    })
    await flushPromises()
    const confirmModal = wrapper.findComponent(ConfirmModal)

    wrapper.vm.remove(BACKUP)
    expect(service.deleteBackup).not.toHaveBeenCalled()
    confirmModal.vm.cancel()
    expect(service.deleteBackup).not.toHaveBeenCalled()

    wrapper.vm.remove(BACKUP)
    await confirmModal.vm.confirm()
    expect(service.deleteBackup).toHaveBeenCalledWith(1, 'r4')
    expect(wrapper.vm.backups).toEqual([])

    wrapper.vm.restore(BACKUP)
    expect(service.restoreBackup).not.toHaveBeenCalled()
    // The restore warns that the applications are installed as new ones.
    expect(confirmModal.vm.message).toBe('backupsModal.confirmRestoreMessage')
    confirmModal.vm.confirm()
    expect(service.restoreBackup).toHaveBeenCalledWith(1, 'r4')
  })

  test('deleting a backup schedule waits for confirmation', async () => {
    const schedule = { id: 7, name: 'Nightly', cron: '0 3 * * *' }
    const service = {
      listSchedules: vi.fn().mockResolvedValue({ data: [schedule] }),
      deleteSchedule: vi.fn().mockResolvedValue({}),
    }
    wrapper = await mountSuspended(BackupSchedulesTab, {
      props: {
        workspace: { id: 1, name: 'Acme' },
        destinations: [],
        service: () => service,
      },
    })
    await flushPromises()

    wrapper.vm.remove(schedule)
    expect(service.deleteSchedule).not.toHaveBeenCalled()
    await wrapper.findComponent(ConfirmModal).vm.confirm()
    expect(service.deleteSchedule).toHaveBeenCalledWith(7)
    expect(wrapper.vm.schedules).toEqual([])
  })

  test('the external storage tab confirms a restore and ignores stale lists', async () => {
    const slowA = deferred()
    const service = {
      listRemoteBackups: vi.fn((destination) =>
        destination === 'a'
          ? slowA.promise
          : Promise.resolve({ data: { results: [remoteBackup('b-key')] } })
      ),
      restoreRemoteBackup: vi.fn(pending),
    }
    wrapper = await mountSuspended(RemoteBackupsTab, {
      props: {
        workspace: { id: 1, name: 'Acme' },
        destinations: [
          { name: 'a', type: 's3', purposes: ['backup'] },
          { name: 'b', type: 's3', purposes: ['backup'] },
        ],
        service: () => service,
      },
    })

    // Switch to b while the list of a is still loading, then let a answer late.
    wrapper.vm.selectDestination('b')
    await flushPromises()
    slowA.resolve({ data: { results: [remoteBackup('a-key')] } })
    await flushPromises()

    expect(wrapper.vm.destination).toBe('b')
    expect(wrapper.vm.backups.map((backup) => backup.key)).toEqual(['b-key'])
    expect(wrapper.vm.loading).toBe(false)

    wrapper.vm.restore(wrapper.vm.backups[0])
    expect(service.restoreRemoteBackup).not.toHaveBeenCalled()
    wrapper.findComponent(ConfirmModal).vm.confirm()
    expect(service.restoreRemoteBackup).toHaveBeenCalledWith('b', 1, {
      key: 'b-key',
    })
  })

  test('the external storage tab retries a destination after a failure', async () => {
    const url = '/backups/destinations/a/workspace/1/'
    mock
      .onGet(url)
      .replyOnce(500)
      .onGet(url)
      .reply(200, { results: [remoteBackup('a-key')] })
    wrapper = await mountSuspended(RemoteBackupsTab, {
      props: {
        workspace: { id: 1, name: 'Acme' },
        destinations: [{ name: 'a', type: 's3', purposes: ['backup'] }],
      },
    })
    await flushPromises()
    expect(wrapper.vm.backups).toEqual([])
    expect(wrapper.vm.error.visible).toBe(true)

    wrapper.vm.selectDestination('a')
    await flushPromises()
    expect(
      mock.history.get.filter((request) => request.url === url)
    ).toHaveLength(2)
    expect(wrapper.vm.backups.map((backup) => backup.key)).toEqual(['a-key'])
  })

  test('the datalake export modal lists schedules without any storage', async () => {
    mock.onGet('/data-destinations/').reply(200, [])
    mock.onGet('/database/data-export/schedules/workspace/1/').reply(200, [
      {
        id: 3,
        name: 'Hourly lake',
        database: 2,
        cron: '0 * * * *',
        timezone: 'UTC',
        destination: 'removed',
        table_ids: null,
        is_active: false,
        warnings: [],
      },
    ])
    mock.onDelete('/database/data-export/schedules/3/').reply(204)

    wrapper = await mountSuspended(DataExportModal, {
      props: {
        database: { id: 2, name: 'Sales', tables: [] },
        workspace: { id: 1, name: 'Acme' },
      },
      // Render the modal in place instead of teleporting it to the body.
      global: { stubs: { teleport: true } },
    })
    wrapper.vm.show()
    await flushPromises()

    const text = wrapper.text()
    expect(text).toContain('Hourly lake')
    expect(text).toContain('dataExportModal.noDestinations')
    expect(text).not.toContain('dataExportModal.newSchedule')

    wrapper.vm.remove(wrapper.vm.schedules[0])
    await flushPromises()
    expect(mock.history.delete).toHaveLength(0)
    await wrapper.findComponent(ConfirmModal).vm.confirm()
    expect(mock.history.delete).toHaveLength(1)
    expect(wrapper.vm.schedules).toEqual([])
  })

  test('a finished restore only adds applications of a workspace in the store', async () => {
    const dispatch = vi.fn()
    const getters = { 'workspace/get': (id) => (id === 1 ? { id } : undefined) }
    const component = {
      $store: { dispatch, getters },
      $t: (key) => key,
    }
    const finishedJob = { installed_applications: [{ id: 9 }] }

    await restoredApplicationsFinished(component, finishedJob, 2)
    expect(dispatch).not.toHaveBeenCalledWith(
      'application/forceCreate',
      expect.anything()
    )
    expect(dispatch).toHaveBeenCalledWith('toast/info', expect.anything())

    dispatch.mockClear()
    await restoredApplicationsFinished(component, finishedJob, 1)
    expect(dispatch).toHaveBeenCalledWith('application/forceCreate', { id: 9 })
    expect(dispatch).toHaveBeenCalledWith('toast/info', expect.anything())
  })

  test('the backups modal hides the schedules tab without permission', async () => {
    mock.onGet('/data-destinations/').reply(200, [])
    const mountModal = async (hasPermission) => {
      const result = await mountSuspended(BackupsModal, {
        props: { workspace: { id: 1, name: 'Acme' } },
        global: {
          stubs: { teleport: true },
          mocks: { $hasPermission: () => hasPermission },
        },
      })
      result.vm.show()
      await flushPromises()
      return result
    }

    wrapper = await mountModal(false)
    expect(wrapper.text()).toContain('backupsModal.tabBackups')
    expect(wrapper.text()).not.toContain('backupsModal.tabSchedules')
    wrapper.unmount()

    wrapper = await mountModal(true)
    expect(wrapper.text()).toContain('backupsModal.tabSchedules')
  })

  test('the schedule actions are limited to the owner and workspace admins', async () => {
    setUser({ id: 5, is_staff: false })
    const schedules = [
      { id: 1, name: 'Mine', cron: '0 3 * * *', user_id: 5 },
      { id: 2, name: 'Theirs', cron: '0 3 * * *', user_id: 6 },
    ]
    const service = {
      listSchedules: vi.fn().mockResolvedValue({ data: schedules }),
    }
    const mountTab = (workspace, props = {}, hasPermission = true) =>
      mountSuspended(BackupSchedulesTab, {
        props: {
          workspace,
          destinations: [],
          service: () => service,
          ...props,
        },
        global: { mocks: { $hasPermission: () => hasPermission } },
      })
    const actions = () =>
      wrapper.findAll('.backups__actions').map((row) => row.text())

    // A member sees the actions of their own schedule only.
    wrapper = await mountTab({ id: 1, name: 'Acme', permissions: 'MEMBER' })
    await flushPromises()
    expect(actions()[0]).toContain('backupsModal.runNow')
    expect(actions()[1]).not.toContain('backupsModal.runNow')
    expect(wrapper.findAll('[aria-label="backupsModal.edit"]')).toHaveLength(1)
    wrapper.unmount()

    // A workspace admin sees them on every schedule.
    wrapper = await mountTab({ id: 1, name: 'Acme', permissions: 'ADMIN' })
    await flushPromises()
    expect(wrapper.findAll('[aria-label="backupsModal.edit"]')).toHaveLength(2)
    wrapper.unmount()

    // So does the admin panel, which passes `admin`.
    wrapper = await mountTab({ id: 1, name: 'Acme' }, { admin: true })
    await flushPromises()
    expect(wrapper.findAll('[aria-label="backupsModal.edit"]')).toHaveLength(2)
    wrapper.unmount()

    // Without the permission nothing is offered, not even to the owner.
    wrapper = await mountTab(
      { id: 1, name: 'Acme', permissions: 'MEMBER' },
      {},
      false
    )
    await flushPromises()
    expect(wrapper.findAll('[aria-label="backupsModal.edit"]')).toHaveLength(0)
    expect(wrapper.text()).not.toContain('backupsModal.newSchedule')
  })

  test('running a backup schedule reloads the list', async () => {
    setUser({ id: 5, is_staff: false })
    const schedule = { id: 1, name: 'Mine', cron: '0 3 * * *', user_id: 5 }
    const service = {
      listSchedules: vi.fn().mockResolvedValue({ data: [schedule] }),
      runSchedule: vi.fn().mockResolvedValue({
        data: { id: 91, type: 'export_applications_to_destination' },
      }),
    }
    wrapper = await mountSuspended(BackupSchedulesTab, {
      props: {
        workspace: { id: 1, name: 'Acme' },
        destinations: [],
        service: () => service,
      },
    })
    await flushPromises()
    expect(service.listSchedules).toHaveBeenCalledTimes(1)

    await wrapper.vm.runNow(schedule)
    expect(service.runSchedule).toHaveBeenCalledWith(1)
    expect(service.listSchedules).toHaveBeenCalledTimes(2)
  })

  test('a reopened backups modal keeps the running job of its tab', async () => {
    mock.onGet('/backups/workspace/1/').reply(200, { results: [] })
    const service = {
      startBackup: vi.fn().mockResolvedValue({
        data: {
          id: 77,
          type: 'export_applications_to_destination',
          state: 'started',
          progress_percentage: 10,
        },
      }),
    }
    mock.onGet('/data-destinations/').reply(200, [])
    wrapper = await mountSuspended(BackupsModal, {
      props: { workspace: { id: 1, name: 'Acme' } },
      global: { stubs: { teleport: true } },
    })
    wrapper.vm.show()
    await flushPromises()

    // Start a job from the tab, then close and reopen the modal.
    await vi.waitFor(() =>
      expect(wrapper.findComponent(BackupsTab).exists()).toBe(true)
    )
    let tab = wrapper.findComponent(BackupsTab)
    await tab.vm.run('backup', () => service.startBackup(1, {}))
    expect(tab.vm.job.id).toBe(77)
    expect(wrapper.vm.backupJobs['backups:1']).toEqual({
      id: 77,
      kind: 'backup',
    })

    wrapper.vm.hide()
    await flushPromises()
    wrapper.vm.show()
    await flushPromises()

    await vi.waitFor(() =>
      expect(wrapper.findComponent(BackupsTab).exists()).toBe(true)
    )
    tab = wrapper.findComponent(BackupsTab)
    expect(tab.vm.job.id).toBe(77)
    expect(tab.vm.busy).toBe(true)
    expect(tab.vm.jobKind).toBe('backup')
  })

  test('a tab remounted after its job ended still reports the outcome', async () => {
    const store = useNuxtApp().$store
    await store.dispatch('job/forceCreate', {
      id: 78,
      type: 'export_applications_to_destination',
      state: 'finished',
    })
    const service = {
      listBackups: vi.fn().mockResolvedValue({ data: { results: [] } }),
    }
    const dispatch = vi.spyOn(store, 'dispatch')
    wrapper = await mountSuspended(BackupsTab, {
      props: {
        workspace: { id: 1, name: 'Acme' },
        destinations: [],
        service: () => service,
      },
      global: {
        provide: { backupJobs: { 'backups:1': { id: 78, kind: 'backup' } } },
      },
    })
    await flushPromises()

    const toasts = dispatch.mock.calls.filter(
      ([action]) => action === 'toast/info'
    )
    expect(toasts).toHaveLength(1)
    dispatch.mockRestore()
  })

  test('the external storage tab explains missing storage to members and staff', async () => {
    const mountTab = () =>
      mountSuspended(RemoteBackupsTab, {
        props: {
          workspace: { id: 1, name: 'Acme' },
          destinations: [],
          service: () => ({}),
        },
      })

    setUser({ id: 5, is_staff: false })
    wrapper = await mountTab()
    expect(wrapper.text()).toContain('backupsModal.noBackupDestinations')
    expect(wrapper.text()).not.toContain(
      'backupsModal.noBackupDestinationsStaff'
    )
    wrapper.unmount()

    setUser({ id: 5, is_staff: true })
    wrapper = await mountTab()
    expect(wrapper.text()).toContain('backupsModal.noBackupDestinationsStaff')
  })

  test('the schedule forms reject a name longer than the backend allows', async () => {
    wrapper = await mountSuspended(BackupScheduleForm, {
      props: { destinations: [] },
    })
    wrapper.vm.values.name = 'a'.repeat(101)
    wrapper.vm.submit()
    expect(wrapper.emitted('submit')).toBeUndefined()
    wrapper.vm.values.name = 'a'.repeat(100)
    wrapper.vm.submit()
    expect(wrapper.emitted('submit')).toHaveLength(1)
    wrapper.unmount()

    wrapper = await mountSuspended(DataExportScheduleForm, {
      props: {
        database: { id: 1, name: 'Sales', tables: [] },
        destinations: [{ name: 'lake', type: 's3' }],
      },
    })
    wrapper.vm.values.name = 'a'.repeat(101)
    wrapper.vm.submit()
    expect(wrapper.emitted('submit')).toBeUndefined()
    wrapper.vm.values.name = 'a'.repeat(100)
    wrapper.vm.submit()
    expect(wrapper.emitted('submit')).toHaveLength(1)
  })

  test('the schedule forms offer timezones through a searchable dropdown', async () => {
    wrapper = await mountSuspended(BackupScheduleForm, {
      props: { destinations: [] },
    })
    const { data } = wrapper.vm.fetchTimezonePage(1, 'europe/ams')
    expect(data.results).toEqual([
      { id: 'Europe/Amsterdam', value: 'Europe/Amsterdam' },
    ])
    expect(wrapper.vm.fetchTimezonePage(1, '').data.next).toBe(2)
  })

  test('the confirm modal keeps loading until the action settles', async () => {
    wrapper = await mountSuspended(ConfirmModal, {
      global: { stubs: { teleport: true } },
    })
    const action = deferred()
    wrapper.vm.ask({
      title: 't',
      message: 'm',
      onConfirm: () => action.promise,
    })

    const confirmed = wrapper.vm.confirm()
    expect(wrapper.vm.loading).toBe(true)
    // A second click neither runs the action again nor cancels it.
    wrapper.vm.cancel()
    expect(wrapper.vm.loading).toBe(true)

    action.resolve()
    await confirmed
    expect(wrapper.vm.loading).toBe(false)
  })

  test('only the owner or a workspace admin can run a datalake schedule', async () => {
    setUser({ id: 5, is_staff: false })
    mock.onGet('/data-destinations/').reply(200, [])
    mock.onGet('/database/data-export/schedules/workspace/1/').reply(200, [
      { id: 3, name: 'Mine', database: 2, user_id: 5, table_ids: null },
      { id: 4, name: 'Theirs', database: 2, user_id: 6, table_ids: null },
    ])
    const mountModal = async (permissions) => {
      const result = await mountSuspended(DataExportModal, {
        props: {
          database: { id: 2, name: 'Sales', tables: [] },
          workspace: { id: 1, name: 'Acme', permissions },
        },
        global: { stubs: { teleport: true } },
      })
      result.vm.show()
      await flushPromises()
      return result
    }

    wrapper = await mountModal('MEMBER')
    expect(wrapper.text().match(/dataExportModal\.runNow/g)).toHaveLength(1)
    wrapper.unmount()

    wrapper = await mountModal('ADMIN')
    expect(wrapper.text().match(/dataExportModal\.runNow/g)).toHaveLength(2)
  })

  test('the datalake modal ignores stale runs and resets when reopened', async () => {
    setUser({ id: 5, is_staff: true })
    mock.onGet('/data-destinations/').reply(200, [])
    mock.onGet('/database/data-export/schedules/workspace/1/').reply(200, [
      { id: 3, name: 'A', database: 2, user_id: 5, table_ids: null },
      { id: 4, name: 'B', database: 2, user_id: 5, table_ids: null },
    ])
    const slow = deferred()
    mock
      .onGet('/database/data-export/schedules/3/runs/')
      .reply(() => slow.promise)
    mock
      .onGet('/database/data-export/schedules/4/runs/')
      .reply(200, [{ id: 2, state: 'finished', mode: 'full', table_id: 1 }])

    wrapper = await mountSuspended(DataExportModal, {
      props: {
        database: { id: 2, name: 'Sales', tables: [] },
        workspace: { id: 1, name: 'Acme' },
      },
      global: { stubs: { teleport: true } },
    })
    wrapper.vm.show()
    await flushPromises()

    const first = wrapper.vm.toggleRuns(wrapper.vm.schedules[0])
    await wrapper.vm.toggleRuns(wrapper.vm.schedules[1])
    expect(wrapper.vm.runs.map((run) => run.id)).toEqual([2])

    // The answer for the first schedule arrives late and must be dropped.
    slow.resolve([200, [{ id: 1, state: 'failed', mode: 'auto', table_id: 1 }]])
    await first
    await flushPromises()
    expect(wrapper.vm.runs.map((run) => run.id)).toEqual([2])
    expect(wrapper.vm.runsLoading).toBe(false)

    wrapper.vm.show()
    expect(wrapper.vm.runs).toEqual([])
    expect(wrapper.vm.openRunsId).toBeNull()
    expect(wrapper.vm.loaded).toBe(false)
  })

  test('a schedule row shows its last run and what it covers', async () => {
    setUser({ id: 5, is_staff: true })
    const schedules = [
      {
        id: 1,
        name: 'Nightly',
        cron: '0 3 * * *',
        is_active: true,
        user_id: 5,
        last_run_on: '2026-02-01T03:00:00+00:00',
        only_structure: true,
        application_ids: [1, 2],
        keep_last: 7,
        keep_days: 30,
      },
      { id: 2, name: 'Plain', cron: '0 4 * * *', user_id: 5 },
    ]
    wrapper = await mountSuspended(BackupSchedulesTab, {
      props: {
        workspace: { id: 1, name: 'Acme' },
        destinations: [],
        service: () => ({
          listSchedules: vi.fn().mockResolvedValue({ data: schedules }),
        }),
      },
    })
    await flushPromises()

    const [first, second] = wrapper.findAll('.backups__item')
    expect(first.text()).toContain('backupsModal.lastRunOn')
    expect(first.text()).toContain('backupsModal.structureOnly')
    expect(first.text()).toContain('backupsModal.applicationCount')
    expect(first.text()).toContain('backupsModal.keepLastBadge')
    expect(first.text()).toContain('backupsModal.keepDaysBadge')
    expect(second.text()).not.toContain('backupsModal.lastRunOn')
    expect(second.text()).toContain('backupsModal.allApplications')
  })

  test('a remote backup row shows who made it, where and from which schedule', async () => {
    const service = {
      listRemoteBackups: vi.fn().mockResolvedValue({
        data: {
          results: [
            {
              ...remoteBackup('k1'),
              sha256: 'abcdef0123456789',
              baserow_version: '1.2.3',
              created_by: 'ada@example.com',
              is_this_instance: false,
              schedule_id: 3,
            },
          ],
        },
      }),
      listSchedules: vi
        .fn()
        .mockResolvedValue({ data: [{ id: 3, name: 'Nightly' }] }),
    }
    wrapper = await mountSuspended(RemoteBackupsTab, {
      props: {
        workspace: { id: 1, name: 'Acme' },
        destinations: [{ name: 'a', type: 's3', purposes: ['backup'] }],
        service: () => service,
      },
    })
    await flushPromises()

    const text = wrapper.text()
    expect(text).toContain('backupsModal.version')
    expect(text).toContain('abcdef01')
    expect(text).not.toContain('abcdef0123')
    expect(text).toContain('backupsModal.createdBy')
    expect(text).toContain('backupsModal.otherInstance')
    expect(text).toContain('backupsModal.fromSchedule')
    expect(wrapper.vm.scheduleName(wrapper.vm.backups[0])).toBe('Nightly')
  })

  test('the trust checkbox needs a staff user and a destination that allows it', async () => {
    const mountTab = (allow) =>
      mountSuspended(RemoteBackupsTab, {
        props: {
          workspace: { id: 1, name: 'Acme' },
          destinations: [
            {
              name: 'a',
              type: 's3',
              purposes: ['backup'],
              allow_trust_public_key: allow,
            },
          ],
          service: () => ({
            listRemoteBackups: vi.fn().mockResolvedValue({ data: {} }),
          }),
        },
      })

    setUser({ id: 5, is_staff: true })
    wrapper = await mountTab(false)
    expect(wrapper.text()).not.toContain('backupsModal.trustPublicKey')
    wrapper.unmount()

    wrapper = await mountTab(true)
    expect(wrapper.text()).toContain('backupsModal.trustPublicKey')
    wrapper.unmount()

    setUser({ id: 5, is_staff: false })
    wrapper = await mountTab(true)
    expect(wrapper.text()).not.toContain('backupsModal.trustPublicKey')
  })

  test('switching storage drops the trust given to the previous one', async () => {
    setUser({ id: 5, is_staff: true })
    const destination = (name) => ({
      name,
      type: 's3',
      purposes: ['backup'],
      allow_trust_public_key: true,
    })
    wrapper = await mountSuspended(RemoteBackupsTab, {
      props: {
        workspace: { id: 1, name: 'Acme' },
        destinations: [destination('a'), destination('b')],
        service: () => ({
          listRemoteBackups: vi.fn().mockResolvedValue({ data: {} }),
          listSchedules: vi.fn().mockResolvedValue({ data: [] }),
        }),
      },
    })
    await flushPromises()

    wrapper.vm.trustPublicKey = true
    wrapper.vm.selectDestination('b')
    await flushPromises()
    expect(wrapper.vm.trustPublicKey).toBe(false)
  })

  test('the restore action needs the permission to create applications', async () => {
    const remoteService = {
      listRemoteBackups: vi
        .fn()
        .mockResolvedValue({ data: { results: [remoteBackup('a-key')] } }),
      listSchedules: vi.fn().mockResolvedValue({ data: [] }),
    }
    const localService = {
      listBackups: vi.fn().mockResolvedValue({ data: { results: [BACKUP] } }),
    }
    const mountTab = async (component, service, props, permissions) => {
      const tab = await mountSuspended(component, {
        props: {
          workspace: { id: 1, name: 'Acme' },
          destinations: [{ name: 'a', type: 's3', purposes: ['backup'] }],
          service: () => service,
          ...props,
        },
        global: {
          mocks: {
            $hasPermission: (operation) => permissions.includes(operation),
          },
        },
      })
      await flushPromises()
      return tab
    }

    for (const [component, service] of [
      [BackupsTab, localService],
      [RemoteBackupsTab, remoteService],
    ]) {
      wrapper = await mountTab(component, service, {}, ['workspace.export'])
      expect(wrapper.text()).not.toContain('backupsModal.restore')
      wrapper.unmount()

      wrapper = await mountTab(component, service, {}, [
        'workspace.create_application',
      ])
      expect(wrapper.text()).toContain('backupsModal.restore')
      wrapper.unmount()

      // Staff in the admin panel are let through by the backend.
      wrapper = await mountTab(component, service, { admin: true }, [])
      expect(wrapper.text()).toContain('backupsModal.restore')
      wrapper.unmount()
      wrapper = null
    }
  })

  test('only a failure other than a missing permission is reported for schedule names', async () => {
    const failure = (status, code) => {
      const error = new Error(code)
      error.response = { status }
      error.handler = { code, notifyIf: vi.fn() }
      return error
    }
    const mountTab = async (error) => {
      wrapper = await mountSuspended(RemoteBackupsTab, {
        props: {
          workspace: { id: 1, name: 'Acme' },
          destinations: [{ name: 'a', type: 's3', purposes: ['backup'] }],
          service: () => ({
            listRemoteBackups: vi.fn().mockResolvedValue({ data: {} }),
            listSchedules: vi.fn().mockRejectedValue(error),
          }),
        },
      })
      await flushPromises()
      expect(wrapper.vm.scheduleNames).toEqual({})
      wrapper.unmount()
      wrapper = null
    }

    const denied = failure(403, 'ERROR_PERMISSION_DENIED')
    await mountTab(denied)
    expect(denied.handler.notifyIf).not.toHaveBeenCalled()

    const broken = failure(500, 'ERROR_UNKNOWN')
    await mountTab(broken)
    expect(broken.handler.notifyIf).toHaveBeenCalled()
  })

  test('datalake runs show their state, mode and error as text', async () => {
    setUser({ id: 5, is_staff: true })
    mock.onGet('/data-destinations/').reply(200, [])
    mock.onGet('/database/data-export/schedules/workspace/1/').reply(200, [
      {
        id: 3,
        name: 'A',
        database: 2,
        user_id: 5,
        table_ids: [1],
        column_naming: 'field_id',
        last_run_on: '2026-02-01T03:00:00+00:00',
      },
    ])
    mock.onGet('/database/data-export/schedules/3/runs/').reply(200, [
      {
        id: 1,
        state: 'failed',
        mode: 'full',
        table_id: 1,
        error: 'bucket is gone',
      },
    ])
    wrapper = await mountSuspended(DataExportModal, {
      props: {
        database: { id: 2, name: 'Sales', tables: [] },
        workspace: { id: 1, name: 'Acme' },
      },
      global: { stubs: { teleport: true } },
    })
    wrapper.vm.show()
    await flushPromises()
    expect(wrapper.text()).toContain('dataExportModal.lastRunOn')
    expect(wrapper.text()).toContain('dataExportModal.tableCount')

    await wrapper.vm.toggleRuns(wrapper.vm.schedules[0])
    const table = wrapper.find('.data-export__runs')
    expect(table.text()).toContain('dataExportModal.runStates.failed')
    expect(table.text()).toContain('dataExportModal.runModes.full')
    expect(table.text()).toContain('bucket is gone')
  })

  test('the admin panel lists the configured destinations read only', async () => {
    mock
      .onGet('/data-destinations/')
      .reply(200, [
        { name: 'offsite', type: 's3', purposes: ['backup', 'datalake'] },
      ])
    wrapper = await mountSuspended(BackupDestinationsCard)
    await flushPromises()

    expect(wrapper.text()).toContain('offsite')
    expect(wrapper.text()).toContain('s3')
    expect(wrapper.text()).toContain('backupsAdminPanel.purposes.datalake')
  })
})
