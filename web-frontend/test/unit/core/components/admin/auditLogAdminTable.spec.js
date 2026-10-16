import MockAdapter from 'axios-mock-adapter'
import { flushPromises } from '@vue/test-utils'
import { mountSuspended } from '@nuxt/test-utils/runtime'
import AuditLogAdminTable from '@baserow/modules/core/components/admin/auditLog/AuditLogAdminTable'
import AuditLogFilters from '@baserow/modules/core/components/admin/auditLog/AuditLogFilters'

const ENTRY = {
  id: 1,
  user_id: 2,
  user_email: 'admin@example.com',
  workspace_id: 3,
  action_type: 'create_table',
  command_type: 'UNDO',
  description: 'Undid creating table',
  created_on: '2026-09-16T10:00:00Z',
  ip_address: '10.0.0.4',
}

describe('audit log admin table', () => {
  let mock = null
  let wrapper = null

  beforeEach(() => {
    mock = new MockAdapter(useNuxtApp().$client, {
      onNoMatch: 'throwException',
    })
    mock.onGet('/admin/audit-log/filter-options/').reply(200, {
      action_types: ['create_table', 'sign_out'],
      command_types: ['DO', 'UNDO', 'REDO', 'AUTH'],
    })
    // jsdom has no working object URL implementation, and the download itself is
    // not what these tests are about.
    window.URL.createObjectURL = vi.fn(() => 'blob:audit-log')
    window.URL.revokeObjectURL = vi.fn()
  })

  afterEach(() => {
    if (wrapper) {
      wrapper.unmount()
      wrapper = null
    }
    mock.restore()
    vi.restoreAllMocks()
  })

  const mountTable = async () => {
    mock
      .onGet('/admin/audit-log/', { params: { page: 1 } })
      .reply(200, { count: 1, results: [ENTRY] })
    const mounted = await mountSuspended(AuditLogAdminTable)
    await flushPromises()
    return mounted
  }

  test('renders the command type and ip address columns', async () => {
    wrapper = await mountTable()

    const keys = wrapper.vm.columns.map((column) => column.key)
    expect(keys).toContain('command_type')
    expect(keys).toContain('ip_address')
    expect(wrapper.text()).toContain('UNDO')
    expect(wrapper.text()).toContain('10.0.0.4')
  })

  test('a filter is sent as a query param without the blank ones', async () => {
    wrapper = await mountTable()

    // `onNoMatch: 'throwException'` is what enforces this: the request fails if an
    // empty `user_id` or `created_after` is tacked on, which the backend would
    // otherwise filter on as an empty string.
    mock
      .onGet('/admin/audit-log/', { params: { page: 1, command_type: 'UNDO' } })
      .reply(200, { count: 1, results: [ENTRY] })

    wrapper.findComponent(AuditLogFilters).vm.setValue('command_type', 'UNDO')
    await flushPromises()

    expect(wrapper.vm.filters).toEqual({ command_type: 'UNDO' })
  })

  test('clearing the filters removes them from the request', async () => {
    wrapper = await mountTable()
    mock
      .onGet('/admin/audit-log/', { params: { page: 1, command_type: 'UNDO' } })
      .reply(200, { count: 1, results: [ENTRY] })

    const filters = wrapper.findComponent(AuditLogFilters).vm
    filters.setValue('command_type', 'UNDO')
    await flushPromises()

    filters.clear()
    await flushPromises()

    expect(wrapper.vm.filters).toEqual({})
  })

  test('the csv export is given the search, sorts and filters on screen', async () => {
    wrapper = await mountTable()
    const exportSpy = vi.spyOn(wrapper.vm.service, 'export')

    mock
      .onGet('/admin/audit-log/', {
        params: { page: 1, search: 'undid', sorts: '+created_on' },
      })
      .reply(200, { count: 1, results: [ENTRY] })
    mock
      .onGet('/admin/audit-log/', {
        params: { page: 1, command_type: 'UNDO', search: 'undid' },
      })
      .reply(200, { count: 1, results: [ENTRY] })
    mock
      .onGet('/admin/audit-log/export/', {
        params: { command_type: 'UNDO', search: 'undid', sorts: '+created_on' },
      })
      .reply(200, 'id,created_on\n1,2026-09-16T10:00:00Z\n')

    const crudTable = wrapper.vm.$refs.crudTable
    crudTable.searchQuery = 'undid'
    crudTable.columnSorts = [{ key: 'created_on', direction: 'desc' }]
    wrapper.findComponent(AuditLogFilters).vm.setValue('command_type', 'UNDO')
    await flushPromises()

    await wrapper.vm.exportCsv()
    await flushPromises()

    // Before the fix this was called with no arguments at all, so a filtered
    // table exported the entire log.
    expect(exportSpy).toHaveBeenCalledWith(
      'undid',
      [{ key: 'created_on', direction: 'desc' }],
      { command_type: 'UNDO' }
    )
  })

  test('the export sends no search when the table has not been searched', async () => {
    wrapper = await mountTable()
    const exportSpy = vi.spyOn(wrapper.vm.service, 'export')

    mock.onGet('/admin/audit-log/export/', { params: {} }).reply(200, 'id\n')

    await wrapper.vm.exportCsv()
    await flushPromises()

    // CrudTable starts `searchQuery` as `false`, which must not reach the query.
    expect(exportSpy).toHaveBeenCalledWith(null, [], {})
  })
})
