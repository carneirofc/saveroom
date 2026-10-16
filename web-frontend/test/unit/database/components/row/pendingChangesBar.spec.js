import { flushPromises } from '@vue/test-utils'

import { TestApp } from '@baserow/test/helpers/testApp'
import PendingChangesBar from '@baserow/modules/database/components/row/PendingChangesBar'
import { notifyIf } from '@baserow/modules/core/utils/error'

vi.mock('@baserow/modules/core/utils/error', async (importOriginal) => ({
  ...(await importOriginal()),
  notifyIf: vi.fn(),
}))

describe('PendingChangesBar', () => {
  let testApp = null
  const table = { id: 1, require_edit_confirmation: true }
  const field = { id: 10, type: 'text' }
  const fields = [field]

  beforeEach(() => {
    testApp = new TestApp()
  })

  afterEach(async () => {
    await testApp.afterEach()
    vi.restoreAllMocks()
    vi.clearAllMocks()
  })

  const stage = async (rowId, value) => {
    await testApp.getStore().dispatch('pendingRowChanges/stage', {
      table,
      row: { id: rowId, field_10: 'old' },
      field,
      value,
      oldValue: 'old',
    })
  }

  const mountBar = async (props = {}) => {
    const wrapper = await testApp.mount(PendingChangesBar, {
      props: { table, fields, ...props },
    })
    const dispatch = vi
      .spyOn(testApp.getStore(), 'dispatch')
      .mockResolvedValue(undefined)
    return { wrapper, dispatch }
  }

  const pressCtrlS = () => {
    document.body.dispatchEvent(
      new KeyboardEvent('keydown', { key: 'S', ctrlKey: true, bubbles: true })
    )
  }

  test('is hidden without pending changes', async () => {
    const { wrapper } = await mountBar()

    expect(wrapper.find('.pending-changes-bar').exists()).toBe(false)
  })

  test('shows the number of pending changes', async () => {
    await stage(5, 'a')
    await stage(6, 'b')
    const { wrapper } = await mountBar({ inline: true })

    expect(wrapper.find('.pending-changes-bar').exists()).toBe(true)
    expect(wrapper.find('.pending-changes-bar--inline').exists()).toBe(true)
    expect(wrapper.vm.count).toBe(2)
  })

  test('saves the pending changes and shows a toast', async () => {
    await stage(5, 'a')
    const { wrapper, dispatch } = await mountBar({ storePrefix: 'template/' })

    await wrapper.vm.save()
    await flushPromises()

    expect(dispatch).toHaveBeenCalledWith('pendingRowChanges/save', {
      table,
      fields,
      storePrefix: 'template/',
    })
    expect(dispatch).toHaveBeenCalledWith(
      'toast/success',
      expect.objectContaining({ title: expect.any(String) })
    )
  })

  test('notifies about a failed save without a success toast', async () => {
    await stage(5, 'a')
    const { wrapper, dispatch } = await mountBar()
    const error = new Error('failed')
    dispatch.mockImplementation((type) =>
      type === 'pendingRowChanges/save'
        ? Promise.reject(error)
        : Promise.resolve()
    )

    await wrapper.vm.save()

    expect(notifyIf).toHaveBeenCalledWith(error, 'row')
    expect(dispatch).not.toHaveBeenCalledWith(
      'toast/success',
      expect.anything()
    )
  })

  test('discards the pending changes', async () => {
    await stage(5, 'a')
    const { wrapper, dispatch } = await mountBar()

    await wrapper.vm.discard()

    expect(dispatch).toHaveBeenCalledWith('pendingRowChanges/discard', {
      table,
      fields,
      storePrefix: 'page/',
    })
  })

  test('Ctrl+S saves when there are pending changes', async () => {
    await stage(5, 'a')
    const { dispatch } = await mountBar()

    pressCtrlS()
    await flushPromises()

    expect(dispatch).toHaveBeenCalledWith(
      'pendingRowChanges/save',
      expect.objectContaining({ table })
    )
  })

  test('Ctrl+S does nothing without pending changes', async () => {
    const { dispatch } = await mountBar()

    pressCtrlS()
    await flushPromises()

    expect(dispatch).not.toHaveBeenCalled()
  })

  test('the inline bar does not listen to Ctrl+S', async () => {
    await stage(5, 'a')
    const { dispatch } = await mountBar({ inline: true })

    pressCtrlS()
    await flushPromises()

    expect(dispatch).not.toHaveBeenCalled()
  })

  test('stops listening to Ctrl+S when unmounted', async () => {
    await stage(5, 'a')
    const { wrapper, dispatch } = await mountBar()

    wrapper.unmount()
    testApp._wrappers = testApp._wrappers.filter((w) => w !== wrapper)
    pressCtrlS()
    await flushPromises()

    expect(dispatch).not.toHaveBeenCalled()
  })
})
