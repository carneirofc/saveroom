import _ from 'lodash'
import { clone } from '@baserow/modules/core/utils/object'

export const IMPORT_MODE_INSERT = 'insert'
export const IMPORT_MODE_UPSERT = 'upsert'
export const IMPORT_MODE_UPDATE = 'update'
export const IMPORT_MODE_REPLACE = 'replace'

export const IMPORT_MODES = [
  IMPORT_MODE_INSERT,
  IMPORT_MODE_UPSERT,
  IMPORT_MODE_UPDATE,
  IMPORT_MODE_REPLACE,
]

/**
 * The modes matching the imported rows with the existing rows using match fields.
 */
export const IMPORT_MATCHING_MODES = [IMPORT_MODE_UPSERT, IMPORT_MODE_UPDATE]

/**
 * Converts the `{ fileColumnIndex: fieldId }` mapping into a list of
 * `[fileColumnIndex, writableFieldIndex]` pairs, ignoring skipped columns and
 * fields that don't exist anymore.
 */
export function getFieldMapping(mapping, fieldIndexMap) {
  return Object.entries(mapping)
    .filter(([, fieldId]) => !!fieldId && fieldIndexMap[fieldId] !== undefined)
    .map(([importIndex, fieldId]) => [
      parseInt(importIndex, 10),
      fieldIndexMap[fieldId],
    ])
}

/**
 * Prepares the parsed file rows for the import endpoints: each row gets one value
 * per writable field, in the backend field order, and the match key values are
 * extracted in the same order as `upsertFieldIds`.
 *
 * @param {Array<Array>} data The parsed file rows.
 * @param {Object} options
 * @param {Object} options.mapping `{ fileColumnIndex: fieldId }`, 0 means skipped.
 * @param {Array<Object>} options.writableFields The writable fields, sorted like
 *   `RowHandler.import_rows` does.
 * @param {Object} options.fieldTypes The field types registry.
 * @param {Object} options.fieldIndexMap `{ fieldId: writableFieldIndex }`.
 * @param {Array<number>} options.upsertFieldIds The match field ids.
 * @param {Function} options.onChunk Awaited after each chunk to keep the UI
 *   responsive.
 * @returns {Promise<{data: Array<Array>, upsertValues: Array<Array>}>}
 */
export async function buildImportPayload(
  data,
  {
    mapping,
    writableFields,
    fieldTypes,
    fieldIndexMap,
    upsertFieldIds = [],
    onChunk = async () => {},
  }
) {
  const fieldMapping = getFieldMapping(mapping, fieldIndexMap)
  const mappedTargetIndexes = new Set(fieldMapping.map(([, target]) => target))

  const upsertTargetIndexes = upsertFieldIds.map((fieldId) => {
    const targetIndex = fieldIndexMap[fieldId]
    if (targetIndex === undefined || !mappedTargetIndexes.has(targetIndex)) {
      throw new Error(`The match field ${fieldId} is not mapped to a column.`)
    }
    return targetIndex
  })

  // Template row with default values
  const defaultRow = writableFields.map((field) =>
    fieldTypes[field.type].getDefaultValue(field, true)
  )

  // Precompute the prepare value function for each field
  const prepareValueByField = writableFields.map((field) => (value) => {
    const fieldType = fieldTypes[field.type]
    return fieldType.prepareValueForUpdate(
      field,
      fieldType.prepareValueForPaste(field, `${value}`, value)
    )
  })

  const rows = []
  const upsertValues = []

  // Processes the data by chunk to avoid UI freezes
  for (const chunk of _.chunk(data, 1000)) {
    for (const row of chunk) {
      const newRow = clone(defaultRow)
      fieldMapping.forEach(([importIndex, targetIndex]) => {
        newRow[targetIndex] = prepareValueByField[targetIndex](row[importIndex])
      })
      rows.push(newRow)
      if (upsertTargetIndexes.length > 0) {
        upsertValues.push(upsertTargetIndexes.map((index) => newRow[index]))
      }
    }
    await onChunk()
  }

  return { data: rows, upsertValues }
}

/**
 * Builds the `configuration` object of the import and import preview endpoints.
 */
export function buildImportConfiguration({
  mode,
  upsertFieldIds = [],
  upsertValues = [],
  skippedFieldIds = [],
  deleteUnmatched = false,
  allowAmbiguousMatches = false,
}) {
  const configuration = { mode }
  if (IMPORT_MATCHING_MODES.includes(mode)) {
    configuration.upsert_fields = upsertFieldIds
    configuration.upsert_values = upsertValues
    configuration.delete_unmatched = deleteUnmatched
    configuration.allow_ambiguous_matches = allowAmbiguousMatches
  }
  if (skippedFieldIds.length > 0) {
    configuration.skipped_fields = skippedFieldIds
  }
  return configuration
}
