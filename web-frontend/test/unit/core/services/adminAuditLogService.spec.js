import MockAdapter from 'axios-mock-adapter'
import AuditLogService, {
  omitEmptyFilters,
} from '@baserow/modules/core/services/admin/auditLog'

describe('admin audit log service', () => {
  let client = null
  let mock = null

  beforeEach(() => {
    client = useNuxtApp().$client
    mock = new MockAdapter(client, { onNoMatch: 'throwException' })
  })

  afterEach(() => {
    mock.restore()
  })

  describe('omitEmptyFilters', () => {
    test('drops blank values but keeps meaningful falsy ones', () => {
      expect(
        omitEmptyFilters({
          user_id: 3,
          workspace_id: null,
          action_type: '',
          command_type: undefined,
          created_after: '2026-01-01T00:00',
          page: 0,
        })
      ).toEqual({
        user_id: 3,
        created_after: '2026-01-01T00:00',
        page: 0,
      })
    })

    test('tolerates no filters at all', () => {
      expect(omitEmptyFilters(undefined)).toEqual({})
    })
  })

  test('fetches the filter options', async () => {
    mock
      .onGet('/admin/audit-log/filter-options/')
      .reply(200, { action_types: ['sign_out'], command_types: ['DO'] })

    const { data } = await AuditLogService(client).fetchFilterOptions()

    expect(data.action_types).toEqual(['sign_out'])
    expect(data.command_types).toEqual(['DO'])
  })

  test('the export sends the search, sorts and filters as query params', async () => {
    mock
      .onGet('/admin/audit-log/export/', {
        params: {
          command_type: 'DO',
          search: 'deleted',
          sorts: '+created_on',
        },
      })
      .reply(200, 'id,created_on\n')

    const { data } = await AuditLogService(client).export(
      'deleted',
      [{ key: 'created_on', direction: 'desc' }],
      { command_type: 'DO' }
    )

    expect(data).toContain('id,created_on')
  })

  test('the export omits filters the user left blank', async () => {
    // `onNoMatch: 'throwException'` makes this fail if an empty `user_id` or
    // `action_type` is sent: the backend would filter on an empty string.
    mock
      .onGet('/admin/audit-log/export/', { params: { command_type: 'UNDO' } })
      .reply(200, 'id\n')

    const { status } = await AuditLogService(client).export(null, [], {
      command_type: 'UNDO',
      user_id: null,
      action_type: '',
      created_after: '',
    })

    expect(status).toBe(200)
  })
})
