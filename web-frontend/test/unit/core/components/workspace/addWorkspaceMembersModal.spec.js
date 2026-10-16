import { flushPromises } from '@vue/test-utils'

import { TestApp } from '@baserow/test/helpers/testApp'
import AddWorkspaceMembersModal from '@baserow/modules/core/components/workspace/AddWorkspaceMembersModal'
import WorkspaceService from '@baserow/modules/core/services/workspace'

vi.mock('@baserow/modules/core/services/workspace', () => ({
  default: vi.fn(),
}))

const ModalStub = {
  name: 'Modal',
  template: '<div><slot /></div>',
  methods: { show: vi.fn(), hide: vi.fn() },
}

describe('AddWorkspaceMembersModal', () => {
  let testApp = null
  const workspace = { id: 3, name: 'Acme' }
  const alice = { user_id: 10, name: 'Alice', email: 'alice@example.com' }
  const bob = { user_id: 11, name: 'Bob', email: 'bob@example.com' }

  beforeEach(() => {
    testApp = new TestApp()
  })

  afterEach(async () => {
    await testApp.afterEach()
    vi.clearAllMocks()
  })

  const mountModal = async (service, props = {}) => {
    WorkspaceService.mockReturnValue(service)
    const wrapper = await testApp.mount(AddWorkspaceMembersModal, {
      props: { workspace, ...props },
      global: { stubs: { Modal: ModalStub } },
    })
    const dispatch = vi
      .spyOn(testApp.getStore(), 'dispatch')
      .mockResolvedValue(undefined)
    return { wrapper, dispatch }
  }

  test('does not search below the minimum length', async () => {
    const searchUserCandidates = vi.fn()
    const { wrapper } = await mountModal({ searchUserCandidates })

    wrapper.vm.search = 'al'
    wrapper.vm.onSearch()
    await flushPromises()

    expect(searchUserCandidates).not.toHaveBeenCalled()
    expect(wrapper.vm.candidates).toEqual([])
  })

  test('searches candidates and keeps only the latest response', async () => {
    let resolveFirst
    const searchUserCandidates = vi
      .fn()
      .mockImplementationOnce(
        () => new Promise((resolve) => (resolveFirst = resolve))
      )
      .mockResolvedValueOnce({ data: [bob] })
    const { wrapper } = await mountModal({ searchUserCandidates })

    wrapper.vm.search = 'ali'
    const first = wrapper.vm.fetchCandidates()
    wrapper.vm.search = 'bob'
    await wrapper.vm.fetchCandidates()
    resolveFirst({ data: [alice] })
    await first
    await flushPromises()

    expect(searchUserCandidates).toHaveBeenNthCalledWith(1, 3, 'ali')
    expect(searchUserCandidates).toHaveBeenNthCalledWith(2, 3, 'bob')
    expect(wrapper.vm.candidates).toEqual([bob])
    expect(wrapper.vm.searching).toBe(false)
  })

  test('toggles the selection', async () => {
    const { wrapper } = await mountModal({})

    wrapper.vm.toggle(alice)
    wrapper.vm.toggle(bob)
    wrapper.vm.toggle(alice)

    expect(wrapper.vm.selected).toEqual([bob])
    expect(wrapper.vm.isSelected(bob)).toBe(true)
    expect(wrapper.vm.isSelected(alice)).toBe(false)
  })

  test('adds the selected users with the chosen permissions', async () => {
    const workspaceUsers = [{ id: 1, user_id: 10, permissions: 'ADMIN' }]
    const addUsers = vi.fn().mockResolvedValue({ data: workspaceUsers })
    const { wrapper, dispatch } = await mountModal({ addUsers })

    wrapper.vm.toggle(alice)
    wrapper.vm.permissions = 'ADMIN'
    await wrapper.vm.add()

    expect(addUsers).toHaveBeenCalledWith(3, [10], 'ADMIN', {
      teamIds: [],
      accessLevel: null,
    })
    expect(dispatch).toHaveBeenCalledWith('workspace/forceAddWorkspaceUser', {
      workspaceId: 3,
      values: workspaceUsers[0],
    })
    expect(wrapper.emitted('added')[0]).toEqual([workspaceUsers])
    expect(wrapper.vm.saving).toBe(false)
  })

  test('shows the error and keeps the selection when adding fails', async () => {
    const apiError = Object.assign(new Error('boom'), {
      handler: {
        handled: false,
        getMessage: () => ({ title: 'x', message: 'y' }),
        handle: vi.fn(),
      },
    })
    const addUsers = vi.fn().mockRejectedValue(apiError)
    const { wrapper } = await mountModal({ addUsers })
    const handleError = vi
      .spyOn(wrapper.vm, 'handleError')
      .mockImplementation(() => {})

    wrapper.vm.toggle(alice)
    await wrapper.vm.add()

    expect(handleError).toHaveBeenCalled()
    expect(wrapper.emitted('added')).toBeUndefined()
    expect(wrapper.vm.selected).toEqual([alice])
    expect(wrapper.vm.saving).toBe(false)
  })

  test('adds the selected users to the chosen teams with a default access level', async () => {
    const addUsers = vi.fn().mockResolvedValue({ data: [] })
    const teams = [
      { id: 7, name: 'Finance' },
      { id: 8, name: 'Ops' },
    ]
    const { wrapper } = await mountModal({ addUsers }, { teams })

    wrapper.vm.toggle(alice)
    wrapper.vm.toggleTeam(teams[0])
    wrapper.vm.toggleTeam(teams[1])
    wrapper.vm.toggleTeam(teams[0])
    wrapper.vm.accessLevel = 'viewer'
    await wrapper.vm.add()

    expect(addUsers).toHaveBeenCalledWith(3, [10], 'MEMBER', {
      teamIds: [8],
      accessLevel: 'viewer',
    })
  })

  test('sends no access level for an admin, who is never restricted', async () => {
    const addUsers = vi.fn().mockResolvedValue({ data: [] })
    const { wrapper } = await mountModal({ addUsers })

    wrapper.vm.toggle(alice)
    wrapper.vm.permissions = 'ADMIN'
    wrapper.vm.accessLevel = 'viewer'
    await wrapper.vm.add()

    expect(addUsers).toHaveBeenCalledWith(3, [10], 'ADMIN', {
      teamIds: [],
      accessLevel: null,
    })
  })

  test('show resets the previous state', async () => {
    const { wrapper } = await mountModal({})
    wrapper.vm.search = 'alice'
    wrapper.vm.toggle(alice)
    wrapper.vm.toggleTeam({ id: 7, name: 'Finance' })
    wrapper.vm.permissions = 'ADMIN'
    wrapper.vm.accessLevel = 'viewer'

    wrapper.vm.show()

    expect(wrapper.vm.search).toBe('')
    expect(wrapper.vm.selected).toEqual([])
    expect(wrapper.vm.selectedTeamIds).toEqual([])
    expect(wrapper.vm.permissions).toBe('MEMBER')
    expect(wrapper.vm.accessLevel).toBe('inherit')
  })
})
