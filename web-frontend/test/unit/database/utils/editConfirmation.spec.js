import {
  confirmDataChange,
  isProtected,
} from '@baserow/modules/database/utils/editConfirmation'

describe('editConfirmation utils', () => {
  test('isProtected reflects the require_edit_confirmation flag', () => {
    expect(isProtected(null)).toBe(false)
    expect(isProtected(undefined)).toBe(false)
    expect(isProtected({})).toBe(false)
    expect(isProtected({ require_edit_confirmation: false })).toBe(false)
    expect(isProtected({ require_edit_confirmation: true })).toBe(true)
  })

  test('confirmDataChange resolves right away for unprotected tables', async () => {
    const store = { dispatch: vi.fn() }

    const confirmed = await confirmDataChange(
      store,
      { id: 1, require_edit_confirmation: false },
      { title: 'Delete row', message: 'Sure?' }
    )

    expect(confirmed).toBe(true)
    expect(store.dispatch).not.toHaveBeenCalled()
  })

  test.each([true, false])(
    'confirmDataChange asks protected tables and resolves %s',
    async (answer) => {
      const store = { dispatch: vi.fn().mockResolvedValue(answer) }
      const options = { title: 'Delete row', message: 'Sure?', danger: true }

      const confirmed = await confirmDataChange(
        store,
        { id: 1, require_edit_confirmation: true },
        options
      )

      expect(confirmed).toBe(answer)
      expect(store.dispatch).toHaveBeenCalledWith(
        'pendingRowChanges/confirm',
        options
      )
    }
  )
})
