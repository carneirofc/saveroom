import { flushPromises } from '@vue/test-utils'

import { TestApp } from '@baserow/test/helpers/testApp'
import DatabaseAccessModal from '@baserow/modules/database/components/access/DatabaseAccessModal'
import AccessService from '@baserow/modules/database/services/access'

vi.mock('@baserow/modules/database/services/access', () => ({
  default: vi.fn(),
}))

const ModalStub = {
  name: 'Modal',
  template: '<div><slot /></div>',
  methods: { show: vi.fn(), hide: vi.fn() },
}

const subjects = [
  {
    subject_type: 'team',
    subject_id: 1,
    name: 'Finance',
    email: null,
    is_admin: false,
    level: 'viewer',
    inherited_level: null,
    inherited_from: null,
  },
  {
    subject_type: 'user',
    subject_id: 1,
    name: 'Alice',
    email: 'alice@example.com',
    is_admin: false,
    level: null,
    inherited_level: 'editor',
    inherited_from: 'database',
  },
  {
    subject_type: 'user',
    subject_id: 2,
    name: 'Admin',
    email: 'admin@example.com',
    is_admin: true,
    level: null,
    inherited_level: null,
    inherited_from: null,
  },
]

describe('DatabaseAccessModal', () => {
  let testApp = null

  beforeEach(() => {
    testApp = new TestApp()
  })

  afterEach(async () => {
    await testApp.afterEach()
    vi.clearAllMocks()
  })

  const mountModal = async (service) => {
    AccessService.mockReturnValue(service)
    const wrapper = await testApp.mount(DatabaseAccessModal, {
      props: {
        workspace: { id: 3 },
        scopeType: 'table',
        scopeId: 9,
        scopeName: 'Invoices',
      },
      global: { stubs: { Modal: ModalStub } },
    })
    const dispatch = vi
      .spyOn(testApp.getStore(), 'dispatch')
      .mockResolvedValue(undefined)
    return { wrapper, dispatch }
  }

  test('loads the subjects of the scope when shown', async () => {
    const get = vi.fn().mockResolvedValue({ data: { subjects } })
    const { wrapper } = await mountModal({ get })

    wrapper.vm.show()
    await flushPromises()

    expect(get).toHaveBeenCalledWith('table', 9)
    expect(wrapper.vm.subjects).toEqual(subjects)
    expect(wrapper.vm.loading).toBe(false)
    expect(wrapper.vm.hasChanges).toBe(false)
  })

  test('shows the saved level, inherit, and pending selections', async () => {
    const get = vi.fn().mockResolvedValue({ data: { subjects } })
    const { wrapper } = await mountModal({ get })
    wrapper.vm.show()
    await flushPromises()

    const [team, alice] = subjects
    expect(wrapper.vm.levelOf(team)).toBe('viewer')
    expect(wrapper.vm.levelOf(alice)).toBe('inherit')

    wrapper.vm.setLevel(alice, 'none')
    expect(wrapper.vm.levelOf(alice)).toBe('none')
    expect(wrapper.vm.hasChanges).toBe(true)
  })

  test('describes what a subject inherits', async () => {
    const { wrapper } = await mountModal({})
    const [team, alice, admin] = subjects

    expect(wrapper.vm.inheritedHint(admin)).toBe('')
    expect(wrapper.vm.inheritedHint(alice)).toContain('database')
    expect(wrapper.vm.inheritedHint(team)).toBeTruthy()
  })

  test('saves only the changed grants and closes', async () => {
    const get = vi.fn().mockResolvedValue({ data: { subjects } })
    const updated = subjects.map((s) =>
      s.subject_type === 'user' && s.subject_id === 1
        ? { ...s, level: 'none' }
        : s
    )
    const set = vi.fn().mockResolvedValue({ data: { subjects: updated } })
    const { wrapper, dispatch } = await mountModal({ get, set })
    wrapper.vm.show()
    await flushPromises()
    const hide = vi.spyOn(wrapper.vm, 'hide').mockImplementation(() => {})

    const [team, alice] = subjects
    wrapper.vm.setLevel(team, 'viewer') // unchanged
    wrapper.vm.setLevel(alice, 'none')
    await wrapper.vm.save()

    expect(set).toHaveBeenCalledWith('table', 9, [
      { subject_type: 'user', subject_id: 1, level: 'none' },
    ])
    expect(wrapper.vm.subjects).toEqual(updated)
    expect(wrapper.vm.hasChanges).toBe(false)
    expect(dispatch).toHaveBeenCalledWith(
      'toast/success',
      expect.objectContaining({ title: expect.any(String) })
    )
    expect(hide).toHaveBeenCalled()
  })

  test('does not call the API without changes', async () => {
    const set = vi.fn()
    const { wrapper } = await mountModal({ set })

    await wrapper.vm.save()

    expect(set).not.toHaveBeenCalled()
  })

  test('keeps pending changes when saving fails', async () => {
    const get = vi.fn().mockResolvedValue({ data: { subjects } })
    const set = vi.fn().mockRejectedValue(new Error('boom'))
    const { wrapper } = await mountModal({ get, set })
    wrapper.vm.show()
    await flushPromises()
    const handleError = vi
      .spyOn(wrapper.vm, 'handleError')
      .mockImplementation(() => {})

    wrapper.vm.setLevel(subjects[1], 'builder')
    await wrapper.vm.save()

    expect(handleError).toHaveBeenCalled()
    expect(wrapper.vm.hasChanges).toBe(true)
    expect(wrapper.vm.saving).toBe(false)
  })
})
