import pendingRowChanges from '@baserow/modules/database/store/pendingRowChanges'
import rowModal from '@baserow/modules/database/store/rowModal'
import RowService from '@baserow/modules/database/services/row'
import { TestApp } from '@baserow/test/helpers/testApp'

vi.mock('@baserow/modules/database/services/row', () => ({
  default: vi.fn(),
}))

describe('pendingRowChanges store', () => {
  let testApp = null
  let store = null
  const table = { id: 1, require_edit_confirmation: true }
  const field = { id: 10, type: 'text' }
  const otherField = { id: 11, type: 'text' }

  beforeEach(() => {
    testApp = new TestApp()
    store = testApp.createStore({
      modules: {
        pendingRowChanges,
        rowModal,
      },
    })
  })

  afterEach(() => {
    testApp.afterEach()
    vi.restoreAllMocks()
    RowService.mockReset()
  })

  const stageCell = (
    rowId,
    fieldToStage,
    value,
    oldValue,
    stageTable = table
  ) =>
    store.dispatch('pendingRowChanges/stage', {
      table: stageTable,
      row: { id: rowId, [`field_${fieldToStage.id}`]: oldValue },
      field: fieldToStage,
      value,
      oldValue,
    })

  const spyOnViewTypes = () =>
    Object.values(store.$registry.getAll('view')).map((viewType) =>
      vi.spyOn(viewType, 'rowUpdated').mockResolvedValue(undefined)
    )

  const batchUpdateResponse = (items) => ({
    data: {
      items: items.map((item) => ({ ...item })),
      metadata: { updated_field_ids: [10] },
    },
  })

  test('stage keeps the first old value and counts changed cells', async () => {
    const row = { id: 5, field_10: 'a', field_11: 'x' }
    await store.dispatch('pendingRowChanges/stage', {
      table,
      row,
      field,
      value: 'b',
      oldValue: 'a',
    })
    await store.dispatch('pendingRowChanges/stage', {
      table,
      row,
      field,
      value: 'c',
      oldValue: 'b',
    })
    await store.dispatch('pendingRowChanges/stage', {
      table,
      row,
      field: otherField,
      value: 'y',
      oldValue: 'x',
    })

    expect(store.getters['pendingRowChanges/count'](table.id)).toBe(2)
    expect(store.getters['pendingRowChanges/hasPending'](table.id)).toBe(true)
    expect(
      store.getters['pendingRowChanges/isCellPending'](table.id, row.id, 10)
    ).toBe(true)
    expect(
      store.state.pendingRowChanges.tables[table.id][row.id].fields[10]
    ).toMatchObject({ value: 'c', oldValue: 'a' })
  })

  test('staging the original value again removes the pending change', async () => {
    const row = { id: 5, field_10: 'a' }
    await store.dispatch('pendingRowChanges/stage', {
      table,
      row,
      field,
      value: 'b',
      oldValue: 'a',
    })
    await store.dispatch('pendingRowChanges/stage', {
      table,
      row,
      field,
      value: 'a',
      oldValue: 'b',
    })

    expect(store.getters['pendingRowChanges/count'](table.id)).toBe(0)
    expect(store.getters['pendingRowChanges/hasPending'](table.id)).toBe(false)
  })

  test('forgetRow drops the changes of a deleted row', async () => {
    await store.dispatch('pendingRowChanges/stage', {
      table,
      row: { id: 5, field_10: 'a' },
      field,
      value: 'b',
      oldValue: 'a',
    })
    await store.dispatch('pendingRowChanges/stage', {
      table,
      row: { id: 6, field_10: 'a' },
      field,
      value: 'b',
      oldValue: 'a',
    })

    await store.dispatch('pendingRowChanges/forgetRow', {
      tableId: table.id,
      rowId: 5,
    })

    expect(store.getters['pendingRowChanges/count'](table.id)).toBe(1)
    expect(store.getters['pendingRowChanges/isRowPending'](table.id, 5)).toBe(
      false
    )
  })

  test('confirm resolves with the answer of the mounted host', async () => {
    await store.dispatch('pendingRowChanges/registerConfirmationHost')

    const confirmed = store.dispatch('pendingRowChanges/confirm', {
      title: 'Delete row',
      message: 'Sure?',
      danger: true,
    })
    expect(store.getters['pendingRowChanges/getConfirmation']).toMatchObject({
      title: 'Delete row',
      danger: true,
    })
    await store.dispatch('pendingRowChanges/resolveConfirmation', true)
    expect(await confirmed).toBe(true)
    expect(store.getters['pendingRowChanges/getConfirmation']).toBe(null)

    const cancelled = store.dispatch('pendingRowChanges/confirm', {
      title: 'Delete row',
      message: 'Sure?',
    })
    await store.dispatch('pendingRowChanges/resolveConfirmation', false)
    expect(await cancelled).toBe(false)
  })

  test('unmounting the last host cancels an open confirmation', async () => {
    await store.dispatch('pendingRowChanges/registerConfirmationHost')
    const pending = store.dispatch('pendingRowChanges/confirm', {
      title: 'Move row',
      message: 'Sure?',
    })
    await store.dispatch('pendingRowChanges/unregisterConfirmationHost')
    expect(await pending).toBe(false)
  })

  test('stage updates an open row modal with the staged value', async () => {
    const dispatch = vi.spyOn(store, 'dispatch')

    await stageCell(5, field, 'b', 'a')

    expect(dispatch).toHaveBeenCalledWith('rowModal/updated', {
      tableId: table.id,
      values: { id: 5, field_10: 'b' },
    })
  })

  test('pending changes are tracked per table', async () => {
    const otherTable = { id: 2, require_edit_confirmation: true }

    await stageCell(5, field, 'b', 'a')
    await stageCell(5, field, 'c', 'a', otherTable)
    await stageCell(6, field, 'c', 'a', otherTable)

    expect(store.getters['pendingRowChanges/count'](table.id)).toBe(1)
    expect(store.getters['pendingRowChanges/count'](otherTable.id)).toBe(2)
    expect(store.getters['pendingRowChanges/count'](999)).toBe(0)
    expect(store.getters['pendingRowChanges/hasPending'](999)).toBe(false)
    expect(
      store.getters['pendingRowChanges/isCellPending'](table.id, 5, 11)
    ).toBe(false)
    expect(store.getters['pendingRowChanges/isRowPending'](999, 5)).toBe(false)
  })

  test('staged values are compared by content, not identity', async () => {
    const arrayField = { id: 12, type: 'multiple_select' }
    await stageCell(5, arrayField, [{ id: 1 }], [])
    await stageCell(5, arrayField, [], [{ id: 1 }])

    expect(store.getters['pendingRowChanges/hasPending'](table.id)).toBe(false)
  })

  test('forgetRow of an unknown table or the last row clears the table', async () => {
    await store.dispatch('pendingRowChanges/forgetRow', {
      tableId: 999,
      rowId: 1,
    })
    expect(store.state.pendingRowChanges.tables).toEqual({})

    await stageCell(5, field, 'b', 'a')
    await store.dispatch('pendingRowChanges/forgetRow', {
      tableId: table.id,
      rowId: 5,
    })
    expect(store.state.pendingRowChanges.tables[table.id]).toBeUndefined()
  })

  test('discard without pending changes does nothing', async () => {
    const rowUpdatedSpies = spyOnViewTypes()

    await store.dispatch('pendingRowChanges/discard', { table, fields: [] })

    rowUpdatedSpies.forEach((spy) => expect(spy).not.toHaveBeenCalled())
  })

  test('discard reverts the staged values in every view and row modal', async () => {
    const rowUpdatedSpies = spyOnViewTypes()
    await stageCell(5, field, 'b', 'a')
    await store.dispatch('pendingRowChanges/stage', {
      table,
      row: { id: 5, field_10: 'b', field_11: 'x' },
      field: otherField,
      value: 'y',
      oldValue: 'x',
    })
    const dispatch = vi.spyOn(store, 'dispatch')

    await store.dispatch('pendingRowChanges/discard', {
      table,
      fields: [field, otherField],
      storePrefix: 'template/',
    })

    expect(store.getters['pendingRowChanges/hasPending'](table.id)).toBe(false)
    expect(rowUpdatedSpies.length).toBeGreaterThan(0)
    rowUpdatedSpies.forEach((spy) => {
      expect(spy).toHaveBeenCalledTimes(1)
      const [, tableId, fields, current, before, , , storePrefix] =
        spy.mock.calls[0]
      expect(tableId).toBe(table.id)
      expect(fields).toEqual([field, otherField])
      expect(current).toMatchObject({ id: 5, field_10: 'b', field_11: 'y' })
      expect(before).toMatchObject({ id: 5, field_10: 'a', field_11: 'x' })
      expect(storePrefix).toBe('template/')
    })
    expect(dispatch).toHaveBeenCalledWith('rowModal/updated', {
      tableId: table.id,
      values: expect.objectContaining({ id: 5, field_10: 'a', field_11: 'x' }),
    })
  })

  test('save sends one batch update with the prepared values', async () => {
    const rowUpdatedSpies = spyOnViewTypes()
    const batchUpdate = vi.fn(async (tableId, items) =>
      batchUpdateResponse(items)
    )
    RowService.mockReturnValue({ batchUpdate })
    const fieldType = store.$registry.get('field', 'text')
    const prepare = vi.spyOn(fieldType, 'prepareValueForUpdate')

    await stageCell(5, field, 'b', 'a')
    await stageCell(6, field, 'c', 'a')
    await stageCell(6, field, 'd', 'c')

    await store.dispatch('pendingRowChanges/save', { table, fields: [field] })

    expect(batchUpdate).toHaveBeenCalledTimes(1)
    expect(batchUpdate).toHaveBeenCalledWith(table.id, [
      { id: 5, field_10: 'b' },
      { id: 6, field_10: 'd' },
    ])
    expect(prepare).toHaveBeenCalledWith(field, 'd')
    expect(store.getters['pendingRowChanges/hasPending'](table.id)).toBe(false)
    expect(store.getters['pendingRowChanges/isSaving']).toBe(false)
    rowUpdatedSpies.forEach((spy) => {
      expect(spy).toHaveBeenCalledTimes(2)
      const [, , , before, after, , updatedFieldIds] = spy.mock.calls[1]
      expect(before).toMatchObject({ id: 6, field_10: 'a' })
      expect(after).toEqual({ id: 6, field_10: 'd' })
      expect(updatedFieldIds).toEqual([10])
    })
  })

  test('save splits the batch update by the row page size limit', async () => {
    spyOnViewTypes()
    const batchUpdate = vi.fn(async (tableId, items) =>
      batchUpdateResponse(items)
    )
    RowService.mockReturnValue({ batchUpdate })
    store.$config = { public: { baserowRowPageSizeLimit: 2 } }

    for (const rowId of [1, 2, 3, 4, 5]) {
      await stageCell(rowId, field, 'new', 'old')
    }
    await store.dispatch('pendingRowChanges/save', { table, fields: [field] })

    expect(batchUpdate.mock.calls.map(([, items]) => items.length)).toEqual([
      2, 2, 1,
    ])
    expect(store.getters['pendingRowChanges/count'](table.id)).toBe(0)
  })

  test('save marks the store as saving while the request is in flight', async () => {
    spyOnViewTypes()
    let respond = null
    const batchUpdate = vi.fn(
      (tableId, items) =>
        new Promise((resolve) => {
          respond = () => resolve(batchUpdateResponse(items))
        })
    )
    RowService.mockReturnValue({ batchUpdate })
    await stageCell(5, field, 'b', 'a')

    const saving = store.dispatch('pendingRowChanges/save', {
      table,
      fields: [field],
    })
    expect(store.getters['pendingRowChanges/isSaving']).toBe(true)

    // A second save while the first is in flight is ignored.
    await store.dispatch('pendingRowChanges/save', { table, fields: [field] })
    expect(batchUpdate).toHaveBeenCalledTimes(1)

    respond()
    await saving
    expect(store.getters['pendingRowChanges/isSaving']).toBe(false)
  })

  test('a failed save keeps the pending changes', async () => {
    spyOnViewTypes()
    const error = new Error('Network error')
    RowService.mockReturnValue({
      batchUpdate: vi.fn().mockRejectedValue(error),
    })
    await stageCell(5, field, 'b', 'a')

    await expect(
      store.dispatch('pendingRowChanges/save', { table, fields: [field] })
    ).rejects.toBe(error)

    expect(store.getters['pendingRowChanges/isSaving']).toBe(false)
    expect(
      store.getters['pendingRowChanges/isCellPending'](table.id, 5, 10)
    ).toBe(true)
  })

  test('save without pending changes does not call the backend', async () => {
    const batchUpdate = vi.fn()
    RowService.mockReturnValue({ batchUpdate })

    await store.dispatch('pendingRowChanges/save', { table, fields: [field] })

    expect(batchUpdate).not.toHaveBeenCalled()
  })

  test('confirm falls back to the browser dialog without a mounted host', async () => {
    // The test environment doesn't implement `window.confirm`, so stub it.
    const originalConfirm = window.confirm
    const browserConfirm = vi.fn().mockReturnValue(true)
    window.confirm = browserConfirm

    try {
      const confirmed = await store.dispatch('pendingRowChanges/confirm', {
        title: 'Delete row',
        message: 'Sure?',
      })

      expect(confirmed).toBe(true)
      expect(browserConfirm).toHaveBeenCalledWith('Delete row\n\nSure?')
      expect(store.getters['pendingRowChanges/getConfirmation']).toBe(null)
    } finally {
      window.confirm = originalConfirm
    }
  })

  test('a new confirmation cancels the one that is still open', async () => {
    await store.dispatch('pendingRowChanges/registerConfirmationHost')

    const first = store.dispatch('pendingRowChanges/confirm', {
      title: 'First',
      message: 'Sure?',
    })
    const second = store.dispatch('pendingRowChanges/confirm', {
      title: 'Second',
      message: 'Sure?',
      confirmLabel: 'Go',
    })

    expect(await first).toBe(false)
    expect(store.getters['pendingRowChanges/getConfirmation']).toEqual({
      title: 'Second',
      message: 'Sure?',
      confirmLabel: 'Go',
      danger: false,
    })
    await store.dispatch('pendingRowChanges/resolveConfirmation', true)
    expect(await second).toBe(true)
  })

  test('unmounting one of several hosts keeps the confirmation open', async () => {
    await store.dispatch('pendingRowChanges/registerConfirmationHost')
    await store.dispatch('pendingRowChanges/registerConfirmationHost')
    const pending = store.dispatch('pendingRowChanges/confirm', {
      title: 'Move row',
      message: 'Sure?',
    })

    await store.dispatch('pendingRowChanges/unregisterConfirmationHost')
    expect(store.getters['pendingRowChanges/getConfirmation']).not.toBe(null)

    await store.dispatch('pendingRowChanges/resolveConfirmation', true)
    expect(await pending).toBe(true)
  })

  test('resolving without an open confirmation is harmless', async () => {
    await store.dispatch('pendingRowChanges/resolveConfirmation', true)
    expect(store.getters['pendingRowChanges/getConfirmation']).toBe(null)
  })
})
