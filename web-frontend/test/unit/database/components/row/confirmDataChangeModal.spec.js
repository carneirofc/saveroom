import { flushPromises } from '@vue/test-utils'

import { TestApp } from '@baserow/test/helpers/testApp'
import ConfirmDataChangeModal from '@baserow/modules/database/components/row/ConfirmDataChangeModal'

const ModalStub = {
  name: 'Modal',
  template: '<div><slot /></div>',
  emits: ['hidden'],
  methods: { show: vi.fn(), hide: vi.fn() },
}

describe('ConfirmDataChangeModal', () => {
  let testApp = null

  beforeEach(() => {
    testApp = new TestApp()
  })

  afterEach(async () => {
    // Never leave a confirmation promise open for the next test.
    await testApp
      .getStore()
      .dispatch('pendingRowChanges/resolveConfirmation', false)
    await testApp.afterEach()
    vi.clearAllMocks()
  })

  const mountModal = () =>
    testApp.mount(ConfirmDataChangeModal, {
      global: { stubs: { Modal: ModalStub } },
    })

  const confirm = (options) =>
    testApp.getStore().dispatch('pendingRowChanges/confirm', options)

  test('registers itself as confirmation host while mounted', async () => {
    const store = testApp.getStore()
    const wrapper = await mountModal()
    expect(store.state.pendingRowChanges.confirmationHosts).toBe(1)

    wrapper.unmount()
    testApp._wrappers = testApp._wrappers.filter((w) => w !== wrapper)
    expect(store.state.pendingRowChanges.confirmationHosts).toBe(0)
  })

  test('shows the requested confirmation', async () => {
    const wrapper = await mountModal()

    confirm({ title: 'Delete row', message: 'Delete this row?', danger: true })
    await flushPromises()

    expect(ModalStub.methods.show).toHaveBeenCalled()
    expect(wrapper.text()).toContain('Delete row')
    expect(wrapper.text()).toContain('Delete this row?')
    expect(wrapper.findComponent({ name: 'Button' }).props('type')).toBe(
      'danger'
    )
  })

  test('uses the custom confirm label and primary type', async () => {
    const wrapper = await mountModal()

    confirm({ title: 'Move row', message: 'Sure?', confirmLabel: 'Move it' })
    await flushPromises()

    const button = wrapper.findComponent({ name: 'Button' })
    expect(button.props('type')).toBe('primary')
    expect(button.text()).toContain('Move it')
  })

  test.each([
    [true, 'confirm'],
    [false, 'cancel'],
  ])('resolves %s when the user clicks %s', async (expected) => {
    const wrapper = await mountModal()

    const answer = confirm({ title: 'Clear cells', message: 'Sure?' })
    await flushPromises()
    await wrapper.vm.resolve(expected)
    await flushPromises()

    expect(await answer).toBe(expected)
    expect(ModalStub.methods.hide).toHaveBeenCalled()
    expect(
      testApp.getStore().getters['pendingRowChanges/getConfirmation']
    ).toBe(null)
  })

  test('closing the modal in another way cancels the confirmation', async () => {
    const wrapper = await mountModal()

    const answer = confirm({ title: 'Paste', message: 'Sure?' })
    await flushPromises()
    wrapper.findComponent(ModalStub).vm.$emit('hidden')
    await flushPromises()

    expect(await answer).toBe(false)
  })

  test('hiding without an open confirmation does not resolve anything', async () => {
    const wrapper = await mountModal()
    const dispatch = vi.spyOn(testApp.getStore(), 'dispatch')

    wrapper.findComponent(ModalStub).vm.$emit('hidden')
    await flushPromises()

    expect(dispatch).not.toHaveBeenCalledWith(
      'pendingRowChanges/resolveConfirmation',
      expect.anything()
    )
    dispatch.mockRestore()
  })
})
