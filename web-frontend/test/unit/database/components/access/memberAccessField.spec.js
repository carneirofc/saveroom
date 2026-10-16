import { flushPromises } from '@vue/test-utils'

import { TestApp } from '@baserow/test/helpers/testApp'
import MemberAccessField from '@baserow/modules/database/components/access/MemberAccessField'
import AccessService from '@baserow/modules/database/services/access'

vi.mock('@baserow/modules/database/services/access', () => ({
  default: vi.fn(),
}))

describe('MemberAccessField', () => {
  let testApp = null
  const column = { additionalProps: { workspaceId: 4 } }

  beforeEach(() => {
    testApp = new TestApp()
  })

  afterEach(async () => {
    await testApp.afterEach()
    vi.clearAllMocks()
  })

  const mountField = async (row, set = vi.fn().mockResolvedValue({})) => {
    AccessService.mockReturnValue({ set })
    const wrapper = await testApp.mount(MemberAccessField, {
      props: { row, column },
    })
    return { wrapper, set }
  }

  test('shows the saved level, and inherit when there is none', async () => {
    const editor = await mountField({
      user_id: 10,
      permissions: 'MEMBER',
      access_level: 'editor',
    })
    const inheriting = await mountField({
      user_id: 11,
      permissions: 'MEMBER',
      access_level: null,
    })

    expect(editor.wrapper.vm.level).toBe('editor')
    expect(inheriting.wrapper.vm.level).toBe('inherit')
  })

  test('saves the chosen level and updates the row', async () => {
    const { wrapper, set } = await mountField({
      user_id: 10,
      permissions: 'MEMBER',
      access_level: null,
    })

    await wrapper.vm.setLevel('viewer')
    await flushPromises()

    expect(set).toHaveBeenCalledWith('workspace', 4, [
      { subject_type: 'user', subject_id: 10, level: 'viewer' },
    ])
    expect(wrapper.emitted('row-update')[0][0].access_level).toBe('viewer')
    expect(wrapper.vm.saving).toBe(false)
  })

  test('inherit removes the grant', async () => {
    const { wrapper, set } = await mountField({
      user_id: 10,
      permissions: 'MEMBER',
      access_level: 'viewer',
    })

    await wrapper.vm.setLevel('inherit')

    expect(set).toHaveBeenCalledWith('workspace', 4, [
      { subject_type: 'user', subject_id: 10, level: null },
    ])
    expect(wrapper.emitted('row-update')[0][0].access_level).toBe(null)
  })

  test('saves nothing when the level did not change', async () => {
    const { wrapper, set } = await mountField({
      user_id: 10,
      permissions: 'MEMBER',
      access_level: 'viewer',
    })

    await wrapper.vm.setLevel('viewer')

    expect(set).not.toHaveBeenCalled()
    expect(wrapper.emitted('row-update')).toBeUndefined()
  })

  test('keeps the row unchanged when saving fails', async () => {
    // `notifyIf` only reports errors that carry a handler and rethrows the rest.
    const apiError = Object.assign(new Error('boom'), {
      handler: { notifyIf: vi.fn() },
    })
    const set = vi.fn().mockRejectedValue(apiError)
    const { wrapper } = await mountField(
      { user_id: 10, permissions: 'MEMBER', access_level: null },
      set
    )

    await wrapper.vm.setLevel('viewer')

    expect(wrapper.emitted('row-update')).toBeUndefined()
    expect(wrapper.vm.saving).toBe(false)
  })

  test('an admin is never restricted', async () => {
    const { wrapper } = await mountField({
      user_id: 10,
      permissions: 'ADMIN',
      access_level: null,
    })

    expect(wrapper.find('.member-access-field__full').exists()).toBe(true)
  })
})
