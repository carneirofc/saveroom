import { flushPromises } from '@vue/test-utils'

import { TestApp } from '@baserow/test/helpers/testApp'
import ImportFileModal from '@baserow/modules/database/components/table/ImportFileModal'
import TableService from '@baserow/modules/database/services/table'

vi.mock('@baserow/modules/database/services/table', () => ({
  default: vi.fn(),
}))

describe('ImportFileModal', () => {
  let testApp = null
  let previewImport = null
  let importData = null

  const database = { id: 1, name: 'Cars', workspace: { id: 10 } }
  const table = { id: 5, name: 'Contacts' }

  const summary = {
    create: 3,
    update: 2,
    unchanged: 1,
    delete: 0,
    skip: 0,
    errors: 0,
  }

  beforeEach(() => {
    testApp = new TestApp()
    previewImport = vi.fn().mockResolvedValue({
      data: {
        summary,
        ambiguous: [],
        ambiguous_blocked: false,
        create: [],
        update: [],
        delete: [],
        skipped: [],
        errors: {},
      },
    })
    importData = vi.fn().mockResolvedValue({
      data: {
        id: 1,
        type: 'file_import',
        state: 'pending',
        progress_percentage: 0,
        report: { failing_rows: {} },
      },
    })
    TableService.mockReturnValue({ previewImport, importData })
  })

  afterEach(async () => {
    await flushPromises()
    await testApp.afterEach()
    vi.clearAllMocks()
  })

  /**
   * The import awaits `$ensureRender`, which waits for an animation frame, so
   * flushing the microtask queue alone isn't enough to let it finish.
   */
  const settle = async (wrapper) => {
    await wrapper.vm.$ensureRender()
    await wrapper.vm.$ensureRender()
    await flushPromises()
  }

  const makeField = (id, name, type) => ({
    id,
    name,
    type,
    primary: id === 100,
    order: id,
    _: { type: testApp.getRegistry().get('field', type) },
  })

  /**
   * Mounts the modal in the state it reaches once a two column file has been parsed
   * and both columns have been mapped onto a field.
   */
  const mountModal = async ({
    tableProps = {},
    data = {},
    hasPermission = () => true,
  } = {}) => {
    const fields = [
      makeField(100, 'Name', 'text'),
      makeField(101, 'Amount', 'number'),
    ]
    const wrapper = await testApp.mount(ImportFileModal, {
      props: { database, table: { ...table, ...tableProps }, fields },
      global: { mocks: { $hasPermission: hasPermission } },
    })
    // The modal resets itself when shown, so the state is set up afterwards.
    wrapper.vm.show()
    await wrapper.vm.$nextTick()
    await wrapper.setData({
      importer: 'excel',
      header: ['Name', 'Amount'],
      previewData: [['Ada', '1']],
      dataLoaded: true,
      mapping: { 0: 100, 1: 101 },
      getData: () => [['Ada', '1']],
      ...data,
    })
    return wrapper
  }

  test('importing previews the changes and asks to accept them', async () => {
    const wrapper = await mountModal()

    expect(wrapper.vm.canBeSubmitted).toBe(true)

    await wrapper.vm.submitted()

    expect(previewImport).toHaveBeenCalledTimes(1)
    expect(importData).not.toHaveBeenCalled()
    expect(wrapper.vm.$refs.confirmImportModal.$refs.modal.open).toBe(true)
    expect(wrapper.vm.preview.summary).toEqual(summary)
  })

  test('accepting the confirmation runs the import once', async () => {
    const wrapper = await mountModal()

    await wrapper.vm.submitted()
    wrapper.vm.$refs.confirmImportModal.resolve(true)
    await vi.waitFor(() => expect(importData).toHaveBeenCalledTimes(1))

    expect(importData.mock.calls[0][0]).toBe(table.id)
  })

  test('cancelling the confirmation imports nothing', async () => {
    const wrapper = await mountModal()

    await wrapper.vm.submitted()
    wrapper.vm.$refs.confirmImportModal.resolve(false)
    await settle(wrapper)

    expect(importData).not.toHaveBeenCalled()
  })

  test('a fresh preview is not fetched twice', async () => {
    const wrapper = await mountModal()

    await wrapper.vm.previewChanges()
    await wrapper.vm.submitted()

    expect(previewImport).toHaveBeenCalledTimes(1)
  })

  test('the confirmation shows the counts of the preview', async () => {
    const wrapper = await mountModal()
    await wrapper.vm.submitted()
    await wrapper.vm.$nextTick()

    const counts = wrapper.vm.$refs.confirmImportModal.entries
    expect(counts.map(({ key, count }) => [key, count])).toEqual([
      ['create', 3],
      ['update', 2],
      ['unchanged', 1],
      ['delete', 0],
      ['skip', 0],
      ['errors', 0],
    ])
  })

  test('a failing preview does not open the confirmation', async () => {
    const error = new Error('nope')
    error.handler = {
      getMessage: () => ({ title: 'Error', message: 'nope' }),
      handled: () => {},
    }
    previewImport.mockRejectedValue(error)
    const wrapper = await mountModal()

    await wrapper.vm.submitted()

    expect(wrapper.vm.$refs.confirmImportModal.$refs.modal.open).toBe(false)
    expect(importData).not.toHaveBeenCalled()
  })

  test('staged changes of the table block the import', async () => {
    const protectedTable = { ...table, require_edit_confirmation: true }
    await testApp.getStore().dispatch('pendingRowChanges/stage', {
      table: protectedTable,
      row: { id: 1, field_100: 'old' },
      field: { id: 100, type: 'text' },
      value: 'new',
      oldValue: 'old',
    })

    const wrapper = await mountModal({
      tableProps: { require_edit_confirmation: true },
    })

    expect(wrapper.vm.pendingChangeCount).toBe(1)
    expect(wrapper.vm.canBeSubmitted).toBe(false)
  })

  test('replacing rows needs the replace permission', async () => {
    const wrapper = await mountModal({
      data: { mode: 'replace' },
      hasPermission: (operation) => operation !== 'database.table.replace_rows',
    })

    expect(wrapper.vm.canReplaceRows).toBe(false)
    expect(
      wrapper.vm.modeOptions.find(({ value }) => value === 'replace').disabled
    ).toBe(true)
    expect(wrapper.vm.isDestructive).toBe(true)
    expect(wrapper.vm.canBeSubmitted).toBe(false)
  })

  test('replacing rows is allowed with the replace permission', async () => {
    const wrapper = await mountModal({ data: { mode: 'replace' } })

    expect(wrapper.vm.canReplaceRows).toBe(true)
    expect(
      wrapper.vm.modeOptions.find(({ value }) => value === 'replace').disabled
    ).toBe(false)
    // A destructive import still requires the preview to have been seen.
    expect(wrapper.vm.canBeSubmitted).toBe(false)

    await wrapper.vm.previewChanges()

    expect(wrapper.vm.canBeSubmitted).toBe(true)
  })
})
