import MockAdapter from 'axios-mock-adapter'
import { flushPromises } from '@vue/test-utils'
import { mountSuspended } from '@nuxt/test-utils/runtime'
import ApiClient from '@baserow/modules/core/components/apiClients/ApiClient'
import ApiClientForm from '@baserow/modules/core/components/apiClients/ApiClientForm'
import ApiClientKeyRevealModal from '@baserow/modules/core/components/apiClients/ApiClientKeyRevealModal'
import ApiClientsModal from '@baserow/modules/core/components/apiClients/ApiClientsModal'
import { copyToClipboard } from '@baserow/modules/database/utils/clipboard'

vi.mock('@baserow/modules/database/utils/clipboard', () => ({
  copyToClipboard: vi.fn(),
}))

const client = (overrides = {}) => ({
  id: 8,
  name: 'Offsite sync',
  scopes: ['backup.read'],
  is_active: true,
  keys: [],
  ...overrides,
})

describe('api clients UI', () => {
  let mock = null
  let wrapper = null

  beforeEach(() => {
    mock = new MockAdapter(useNuxtApp().$client, {
      onNoMatch: 'throwException',
    })
  })

  afterEach(() => {
    if (wrapper) {
      wrapper.unmount()
      wrapper = null
    }
    mock.restore()
    vi.clearAllMocks()
  })

  test('the form requires a name and at least one scope', async () => {
    wrapper = await mountSuspended(ApiClientForm)

    wrapper.vm.submit()
    await flushPromises()
    expect(wrapper.emitted('submitted')).toBeUndefined()

    wrapper.vm.values.name = 'Offsite sync'
    wrapper.vm.submit()
    await flushPromises()
    // A name alone is not enough, a client with no scopes could do nothing.
    expect(wrapper.emitted('submitted')).toBeUndefined()

    wrapper.vm.toggleScope('backup.read', true)
    wrapper.vm.submit()
    await flushPromises()

    expect(wrapper.emitted('submitted')[0][0]).toEqual({
      name: 'Offsite sync',
      scopes: ['backup.read'],
    })
  })

  test('the form keeps scopes in the order the backend declares them', async () => {
    wrapper = await mountSuspended(ApiClientForm)

    wrapper.vm.toggleScope('schedule.write', true)
    wrapper.vm.toggleScope('backup.read', true)
    wrapper.vm.toggleScope('contents.read', true)
    wrapper.vm.toggleScope('schedule.write', false)

    expect(wrapper.vm.values.scopes).toEqual(['backup.read', 'contents.read'])
  })

  test('issuing a key hands the secret over once and does not store it', async () => {
    mock.onPost('/api-clients/8/keys/').reply(200, {
      id: 3,
      name: 'ci',
      prefix: 'brk_abc',
      is_usable: true,
      revoked_on: null,
      key: 'brk_abc.thesecret',
    })

    wrapper = await mountSuspended(ApiClient, { props: { client: client() } })

    await wrapper.vm.createKey({ name: 'ci', expires_on: null })
    await flushPromises()

    // The secret is emitted for the reveal modal, but the key kept in the list
    // must not carry it: the backend can never return it again.
    expect(wrapper.emitted('key-created')[0][0]).toBe('brk_abc.thesecret')
    expect(wrapper.vm.client.keys).toHaveLength(1)
    expect(wrapper.vm.client.keys[0].key).toBeUndefined()
    expect(JSON.stringify(wrapper.vm.client.keys)).not.toContain('thesecret')
  })

  test('revoking a key keeps the row and marks it revoked', async () => {
    mock.onDelete('/api-clients/keys/3/').reply(200, {
      id: 3,
      name: 'ci',
      prefix: 'brk_abc',
      is_usable: false,
      revoked_on: '2026-09-16T10:00:00Z',
    })

    const key = {
      id: 3,
      name: 'ci',
      prefix: 'brk_abc',
      is_usable: true,
      revoked_on: null,
    }
    wrapper = await mountSuspended(ApiClient, {
      props: { client: client({ keys: [key] }) },
    })

    await wrapper.vm.revoke(key)
    await flushPromises()

    expect(wrapper.vm.client.keys).toHaveLength(1)
    expect(wrapper.vm.status(wrapper.vm.client.keys[0])).toBe('revoked')
  })

  test('an expired but unrevoked key reads as expired', async () => {
    wrapper = await mountSuspended(ApiClient, { props: { client: client() } })

    expect(
      wrapper.vm.status({ id: 1, revoked_on: null, is_usable: false })
    ).toBe('expired')
    expect(
      wrapper.vm.status({ id: 1, revoked_on: null, is_usable: true })
    ).toBe('active')
  })

  test('deactivating a client is rolled back when the request fails', async () => {
    mock.onPatch('/api-clients/8/').reply(500)

    const props = { client: client() }
    wrapper = await mountSuspended(ApiClient, { props })

    await wrapper.vm.update({ is_active: false }, { is_active: true })
    await flushPromises()

    expect(wrapper.vm.client.is_active).toBe(true)
  })

  test('editing the scopes of a client patches only the scopes', async () => {
    mock
      .onPatch('/api-clients/8/')
      .reply(200, client({ scopes: ['backup.read', 'schedule.read'] }))

    wrapper = await mountSuspended(ApiClient, { props: { client: client() } })

    wrapper.vm.startEditScopes()
    expect(wrapper.vm.scopeDraft).toEqual(['backup.read'])
    wrapper.vm.scopeDraft = ['backup.read', 'schedule.read']
    await wrapper.vm.saveScopes()
    await flushPromises()

    expect(JSON.parse(mock.history.patch[0].data)).toEqual({
      scopes: ['backup.read', 'schedule.read'],
    })
    expect(wrapper.vm.client.scopes).toEqual(['backup.read', 'schedule.read'])
    expect(wrapper.vm.editingScopes).toBe(false)
  })

  test('a failed scope edit keeps the stored scopes and the editor open', async () => {
    mock.onPatch('/api-clients/8/').reply(500)

    wrapper = await mountSuspended(ApiClient, { props: { client: client() } })
    wrapper.vm.startEditScopes()
    wrapper.vm.scopeDraft = ['schedule.read']
    await wrapper.vm.saveScopes()
    await flushPromises()

    expect(wrapper.vm.client.scopes).toEqual(['backup.read'])
    expect(wrapper.vm.editingScopes).toBe(true)
  })

  test('a client cannot be left without any scope', async () => {
    wrapper = await mountSuspended(ApiClient, { props: { client: client() } })
    wrapper.vm.startEditScopes()
    wrapper.vm.scopeDraft = []
    await wrapper.vm.saveScopes()

    expect(mock.history.patch).toHaveLength(0)
  })

  test('the modal lists the clients of the workspace it was opened for', async () => {
    mock
      .onGet('/api-clients/workspace/1/')
      .reply(200, [client({ name: 'Offsite sync' })])

    wrapper = await mountSuspended(ApiClientsModal, {
      props: { workspace: { id: 1, name: 'Acme' } },
    })
    wrapper.vm.show()
    await flushPromises()

    expect(wrapper.vm.clients).toHaveLength(1)
    // Translations are not loaded in unit tests, so only assert on the data.
    expect(wrapper.html()).toContain('Offsite sync')
    expect(wrapper.html()).toContain('backup.read')
  })

  test('a newly created client goes to the top of the list', async () => {
    mock.onGet('/api-clients/workspace/1/').reply(200, [client({ id: 1 })])
    mock
      .onPost('/api-clients/workspace/1/')
      .reply(200, client({ id: 2, name: 'Nightly runner' }))

    wrapper = await mountSuspended(ApiClientsModal, {
      props: { workspace: { id: 1, name: 'Acme' } },
    })
    wrapper.vm.show()
    await flushPromises()

    wrapper.vm.creating = true
    await wrapper.vm.create({ name: 'Nightly runner', scopes: ['backup.read'] })
    await flushPromises()

    expect(wrapper.vm.clients.map((c) => c.id)).toEqual([2, 1])
    expect(wrapper.vm.creating).toBe(false)
  })

  test('the reveal modal shows the secret and forgets it once closed', async () => {
    wrapper = await mountSuspended(ApiClientKeyRevealModal)

    wrapper.vm.show('brk_abc.thesecret')
    await flushPromises()
    expect(wrapper.vm.secret).toBe('brk_abc.thesecret')

    wrapper.vm.copy()
    expect(copyToClipboard).toHaveBeenCalledWith('brk_abc.thesecret')

    wrapper.vm.hide()
    await flushPromises()
    expect(wrapper.vm.secret).toBe('')
    expect(wrapper.html()).not.toContain('thesecret')
  })
})
