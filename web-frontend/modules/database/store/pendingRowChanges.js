import RowService from '@baserow/modules/database/services/row'
import { clone } from '@baserow/modules/core/utils/object'

/**
 * Stages row edits of tables that have protected editing enabled
 * (`table.require_edit_confirmation`). Instead of immediately sending a cell change
 * to the backend, the views stage it here and the user explicitly saves or discards
 * all changes of the table. Saving sends one batch update, which results in a single
 * audit log entry containing the before and after values.
 *
 * It also holds the pending data change confirmation request, which is rendered by
 * the `ConfirmDataChangeModal` host component.
 */

// The resolver of the pending confirmation promise. It's kept outside of the state
// because functions don't belong in the store state.
let confirmationResolver = null

const valuesEqual = (a, b) => JSON.stringify(a) === JSON.stringify(b)

export const state = () => ({
  // {
  //   [tableId]: {
  //     [rowId]: {
  //       // Copy of the row values before the first change was staged.
  //       before: {},
  //       fields: { [fieldId]: { field, value, oldValue } },
  //     },
  //   },
  // }
  tables: {},
  saving: false,
  // Number of mounted `ConfirmDataChangeModal` hosts.
  confirmationHosts: 0,
  // `null` or `{ title, message, confirmLabel, danger }`.
  confirmation: null,
})

export const mutations = {
  STAGE(state, { tableId, row, field, value, oldValue }) {
    if (!state.tables[tableId]) {
      state.tables[tableId] = {}
    }
    const rows = state.tables[tableId]
    if (!rows[row.id]) {
      rows[row.id] = { before: clone(row), fields: {} }
    }
    const fields = rows[row.id].fields
    const existing = fields[field.id]
    const originalValue = existing ? existing.oldValue : oldValue

    if (valuesEqual(value, originalValue)) {
      delete fields[field.id]
      if (Object.keys(fields).length === 0) {
        delete rows[row.id]
      }
    } else {
      fields[field.id] = { field, value, oldValue: originalValue }
    }

    if (Object.keys(rows).length === 0) {
      delete state.tables[tableId]
    }
  },
  REMOVE_ROW(state, { tableId, rowId }) {
    const rows = state.tables[tableId]
    if (!rows) {
      return
    }
    delete rows[rowId]
    if (Object.keys(rows).length === 0) {
      delete state.tables[tableId]
    }
  },
  CLEAR_TABLE(state, tableId) {
    delete state.tables[tableId]
  },
  SET_SAVING(state, value) {
    state.saving = value
  },
  ADD_CONFIRMATION_HOST(state, amount) {
    state.confirmationHosts += amount
  },
  SET_CONFIRMATION(state, value) {
    state.confirmation = value
  },
}

/**
 * Builds the row object before and after the pending changes of a row, based on the
 * snapshot taken when the first change was staged.
 */
const buildBeforeAndAfter = (entry) => {
  const before = clone(entry.before)
  const after = { id: before.id }
  Object.values(entry.fields).forEach(({ field, value, oldValue }) => {
    before[`field_${field.id}`] = oldValue
    after[`field_${field.id}`] = value
  })
  return { before, after }
}

export const actions = {
  /**
   * Stages a changed cell value. The caller is responsible for updating the displayed
   * value in the view store.
   */
  stage({ commit, dispatch }, { table, row, field, value, oldValue }) {
    commit('STAGE', { tableId: table.id, row, field, value, oldValue })
    dispatch(
      'rowModal/updated',
      {
        tableId: table.id,
        values: { id: row.id, [`field_${field.id}`]: value },
      },
      { root: true }
    )
  },
  /**
   * Forgets the pending changes of a row, for example because it has been deleted.
   */
  forgetRow({ commit }, { tableId, rowId }) {
    commit('REMOVE_ROW', { tableId, rowId })
  },
  /**
   * Reverts all the staged changes of the table in every view and row modal.
   */
  async discard({ state, commit }, { table, fields, storePrefix = 'page/' }) {
    const rows = state.tables[table.id]
    if (!rows) {
      return
    }
    const entries = Object.values(rows)
    commit('CLEAR_TABLE', table.id)

    for (const entry of entries) {
      const { before, after } = buildBeforeAndAfter(entry)
      // The displayed row currently contains the staged values, so it moves from the
      // "after" state back to the "before" state.
      const current = { ...clone(entry.before), ...after }
      await notifyViewsOfRowUpdate(
        this,
        table,
        fields,
        current,
        before,
        storePrefix
      )
      this.dispatch('rowModal/updated', { tableId: table.id, values: before })
    }
  },
  /**
   * Sends all the staged changes of the table to the backend using the batch update
   * endpoint and updates the views with the response.
   */
  async save({ state, commit }, { table, fields, storePrefix = 'page/' }) {
    const rows = state.tables[table.id]
    if (!rows || state.saving) {
      return
    }

    const { $client, $registry, $config } = this
    const entries = Object.values(rows)
    const items = entries.map((entry) => {
      const item = { id: entry.before.id }
      Object.values(entry.fields).forEach(({ field, value }) => {
        const fieldType = $registry.get('field', field.type)
        item[`field_${field.id}`] = fieldType.prepareValueForUpdate(
          field,
          value
        )
      })
      return item
    })

    const limit = $config?.public?.baserowRowPageSizeLimit || 200
    commit('SET_SAVING', true)
    try {
      for (let i = 0; i < entries.length; i += limit) {
        const chunkEntries = entries.slice(i, i + limit)
        const { data } = await RowService($client).batchUpdate(
          table.id,
          items.slice(i, i + limit)
        )
        const updatedById = Object.fromEntries(
          data.items.map((item) => [item.id, item])
        )
        const updatedFieldIds = data.metadata?.updated_field_ids || []

        for (const entry of chunkEntries) {
          const rowId = entry.before.id
          const { before } = buildBeforeAndAfter(entry)
          const updated = updatedById[rowId]
          commit('REMOVE_ROW', { tableId: table.id, rowId })
          if (updated) {
            await notifyViewsOfRowUpdate(
              this,
              table,
              fields,
              before,
              updated,
              storePrefix,
              data.metadata?.[rowId],
              updatedFieldIds
            )
            this.dispatch('rowModal/updated', {
              tableId: table.id,
              values: updated,
            })
          }
        }
      }
    } finally {
      commit('SET_SAVING', false)
    }
  },
  /**
   * Asks the user to confirm a change of data. Resolves `true` when confirmed. If no
   * `ConfirmDataChangeModal` host is mounted, the browser confirm dialog is used so
   * that the confirmation can never be skipped.
   */
  confirm({ state, commit }, { title, message, confirmLabel, danger = false }) {
    if (state.confirmationHosts < 1) {
      return Promise.resolve(window.confirm(`${title}\n\n${message}`))
    }
    if (confirmationResolver !== null) {
      confirmationResolver(false)
    }
    return new Promise((resolve) => {
      confirmationResolver = resolve
      commit('SET_CONFIRMATION', { title, message, confirmLabel, danger })
    })
  },
  resolveConfirmation({ commit }, value) {
    const resolver = confirmationResolver
    confirmationResolver = null
    commit('SET_CONFIRMATION', null)
    if (resolver !== null) {
      resolver(value)
    }
  },
  registerConfirmationHost({ commit }) {
    commit('ADD_CONFIRMATION_HOST', 1)
  },
  unregisterConfirmationHost({ commit, dispatch, state }) {
    commit('ADD_CONFIRMATION_HOST', -1)
    if (state.confirmationHosts < 1) {
      dispatch('resolveConfirmation', false)
    }
  },
}

/**
 * Uses the same code path as a real time row update so that every view type updates
 * its buffer, including moving or hiding the row if it no longer matches the
 * filters or sortings.
 */
async function notifyViewsOfRowUpdate(
  store,
  table,
  fields,
  before,
  after,
  storePrefix,
  metadata = undefined,
  updatedFieldIds = undefined
) {
  for (const viewType of Object.values(store.$registry.getAll('view'))) {
    await viewType.rowUpdated(
      { store, app: store },
      table.id,
      fields,
      before,
      after,
      metadata,
      updatedFieldIds,
      storePrefix
    )
  }
}

export const getters = {
  count: (state) => (tableId) =>
    Object.values(state.tables[tableId] || {}).reduce(
      (total, entry) => total + Object.keys(entry.fields).length,
      0
    ),
  hasPending: (state) => (tableId) =>
    Object.keys(state.tables[tableId] || {}).length > 0,
  isRowPending: (state) => (tableId, rowId) =>
    Boolean(state.tables[tableId]?.[rowId]),
  isCellPending: (state) => (tableId, rowId, fieldId) =>
    Boolean(state.tables[tableId]?.[rowId]?.fields[fieldId]),
  isSaving: (state) => state.saving,
  getConfirmation: (state) => state.confirmation,
}

export default {
  namespaced: true,
  state,
  getters,
  actions,
  mutations,
}
