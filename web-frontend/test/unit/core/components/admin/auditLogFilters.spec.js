import MockAdapter from 'axios-mock-adapter'
import { flushPromises } from '@vue/test-utils'
import { mountSuspended } from '@nuxt/test-utils/runtime'
import AuditLogFilters from '@baserow/modules/core/components/admin/auditLog/AuditLogFilters'

describe('audit log filters', () => {
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
  })

  afterEach(() => {
    if (wrapper) {
      wrapper.unmount()
      wrapper = null
    }
    mock.restore()
  })

  const mountFilters = async () => {
    const mounted = await mountSuspended(AuditLogFilters)
    await flushPromises()
    return mounted
  }

  test('offers the action and command types the backend reports', async () => {
    wrapper = await mountFilters()

    expect(wrapper.vm.actionTypes).toEqual(['create_table', 'sign_out'])
    expect(wrapper.vm.commandTypes).toEqual(['DO', 'UNDO', 'REDO', 'AUTH'])
  })

  test('emits only the filters that carry a value', async () => {
    wrapper = await mountFilters()

    wrapper.vm.setValue('command_type', 'UNDO')
    wrapper.vm.setValue('created_after', '2026-09-01T00:00')

    const emitted = wrapper.emitted('update:filters')
    expect(emitted[emitted.length - 1][0]).toEqual({
      command_type: 'UNDO',
      created_after: '2026-09-01T00:00',
    })
  })

  test('deselecting a filter drops it again', async () => {
    wrapper = await mountFilters()

    wrapper.vm.setValue('command_type', 'UNDO')
    // A dropdown's "All" item selects null, which must remove the filter rather
    // than send an empty one.
    wrapper.vm.setValue('command_type', null)

    const emitted = wrapper.emitted('update:filters')
    expect(emitted[emitted.length - 1][0]).toEqual({})
    expect(wrapper.vm.hasFilters).toBe(false)
  })

  test('clearing resets every filter at once', async () => {
    wrapper = await mountFilters()

    wrapper.vm.setValue('user_id', 4)
    wrapper.vm.setValue('action_type', 'create_table')
    expect(wrapper.vm.hasFilters).toBe(true)

    wrapper.vm.clear()

    const emitted = wrapper.emitted('update:filters')
    expect(emitted[emitted.length - 1][0]).toEqual({})
    expect(wrapper.vm.hasFilters).toBe(false)
  })

  test('the user and workspace pickers query the admin listings', async () => {
    wrapper = await mountFilters()

    mock
      .onGet('/admin/users/', { params: { page: 2, search: 'ann' } })
      .reply(200, { count: 1, results: [{ id: 4, username: 'ann@acme.com' }] })
    mock
      .onGet('/admin/workspaces/options/', {
        params: { page: 1, search: 'ac' },
      })
      .reply(200, { count: 1, results: [{ id: 7, value: 'Acme' }] })

    // PaginatedDropdown only fetches when it is opened and swallows errors, so
    // these calls are asserted directly rather than through the dropdown.
    const { data: users } = await wrapper.vm.fetchUsers(2, 'ann')
    const { data: workspaces } = await wrapper.vm.fetchWorkspaces(1, 'ac')

    expect(users.results[0].username).toBe('ann@acme.com')
    expect(workspaces.results[0].value).toBe('Acme')
  })
})
