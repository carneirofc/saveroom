import MockAdapter from 'axios-mock-adapter'
import ApiClientsService from '@baserow/modules/core/services/apiClients'

describe('api clients service', () => {
  let client = null
  let mock = null

  beforeEach(() => {
    client = useNuxtApp().$client
    mock = new MockAdapter(client, { onNoMatch: 'throwException' })
  })

  afterEach(() => {
    mock.restore()
  })

  test('lists and creates clients of a workspace', async () => {
    mock
      .onGet('/api-clients/workspace/1/')
      .reply(200, [{ id: 7, name: 'Offsite sync', scopes: ['backup.read'] }])
    mock
      .onPost('/api-clients/workspace/1/', {
        name: 'Offsite sync',
        scopes: ['backup.read'],
      })
      .reply(200, { id: 8, name: 'Offsite sync' })

    const service = ApiClientsService(client)
    const { data: list } = await service.fetchAll(1)
    const { data: created } = await service.create(1, {
      name: 'Offsite sync',
      scopes: ['backup.read'],
    })

    expect(list[0].id).toBe(7)
    expect(created.id).toBe(8)
  })

  test('reads, updates and deletes a single client', async () => {
    mock.onGet('/api-clients/8/').reply(200, { id: 8, is_active: true })
    mock
      .onPatch('/api-clients/8/', { is_active: false })
      .reply(200, { id: 8, is_active: false })
    mock.onDelete('/api-clients/8/').reply(204)

    const service = ApiClientsService(client)
    const { data: fetched } = await service.get(8)
    const { data: updated } = await service.update(8, { is_active: false })
    const { status } = await service.delete(8)

    expect(fetched.is_active).toBe(true)
    expect(updated.is_active).toBe(false)
    expect(status).toBe(204)
  })

  test('issuing a key sends a null expiry when it never expires', async () => {
    mock
      .onPost('/api-clients/8/keys/', { name: 'ci', expires_on: null })
      .reply(200, { id: 3, prefix: 'brk_abc', key: 'brk_abc.secret' })

    const { data } = await ApiClientsService(client).createKey(8, {
      name: 'ci',
      expires_on: null,
    })

    expect(data.key).toBe('brk_abc.secret')
  })

  test('revoking a key deletes the key resource and returns the record', async () => {
    mock.onDelete('/api-clients/keys/3/').reply(200, {
      id: 3,
      revoked_on: '2026-09-16T10:00:00Z',
      is_usable: false,
    })

    const { data } = await ApiClientsService(client).revokeKey(3)

    expect(data.revoked_on).toBe('2026-09-16T10:00:00Z')
    expect(data.is_usable).toBe(false)
  })
})
