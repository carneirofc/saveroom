import {
  IMPORT_MODE_INSERT,
  IMPORT_MODE_UPDATE,
  IMPORT_MODE_UPSERT,
  buildImportConfiguration,
  buildImportPayload,
  getFieldMapping,
} from '@baserow/modules/database/utils/import'

const textType = {
  getDefaultValue: () => '',
  prepareValueForPaste: (field, text) => text,
  prepareValueForUpdate: (field, value) => value,
}

const numberType = {
  getDefaultValue: () => null,
  prepareValueForPaste: (field, text) => (text === '' ? null : Number(text)),
  prepareValueForUpdate: (field, value) => value,
}

const fieldTypes = { text: textType, number: numberType }

const writableFields = [
  { id: 1, type: 'text' },
  { id: 2, type: 'number' },
  { id: 3, type: 'text' },
]

const fieldIndexMap = { 1: 0, 2: 1, 3: 2 }

describe('Import utils', () => {
  test('getFieldMapping ignores skipped columns and unknown fields', () => {
    expect(getFieldMapping({ 0: 1, 1: 0, 2: 99, 3: 3 }, fieldIndexMap)).toEqual(
      [
        [0, 0],
        [3, 2],
      ]
    )
  })

  test('buildImportPayload orders the match values like the match fields', async () => {
    const onChunk = vi.fn()
    const { data, upsertValues } = await buildImportPayload(
      [
        ['a', 'x', '1'],
        ['b', 'y', '2'],
      ],
      {
        // column 0 -> field 3, column 1 -> field 1, column 2 -> field 2
        mapping: { 0: 3, 1: 1, 2: 2 },
        writableFields,
        fieldTypes,
        fieldIndexMap,
        upsertFieldIds: [2, 3],
        onChunk,
      }
    )

    expect(data).toEqual([
      ['x', 1, 'a'],
      ['y', 2, 'b'],
    ])
    expect(upsertValues).toEqual([
      [1, 'a'],
      [2, 'b'],
    ])
    expect(onChunk).toHaveBeenCalledTimes(1)
  })

  test('buildImportPayload fills unmapped fields with default values', async () => {
    const { data, upsertValues } = await buildImportPayload([['a']], {
      mapping: { 0: 1 },
      writableFields,
      fieldTypes,
      fieldIndexMap,
    })

    expect(data).toEqual([['a', null, '']])
    expect(upsertValues).toEqual([])
  })

  test('buildImportPayload refuses a match field without column', async () => {
    await expect(
      buildImportPayload([['a']], {
        mapping: { 0: 1 },
        writableFields,
        fieldTypes,
        fieldIndexMap,
        upsertFieldIds: [2],
      })
    ).rejects.toThrow('The match field 2 is not mapped to a column.')
  })

  test('buildImportConfiguration only sends the match settings when matching', () => {
    expect(
      buildImportConfiguration({
        mode: IMPORT_MODE_INSERT,
        upsertFieldIds: [1],
        upsertValues: [['a']],
        skippedFieldIds: [2],
        deleteUnmatched: true,
      })
    ).toEqual({ mode: IMPORT_MODE_INSERT, skipped_fields: [2] })

    expect(
      buildImportConfiguration({
        mode: IMPORT_MODE_UPSERT,
        upsertFieldIds: [1, 3],
        upsertValues: [['a', 'b']],
        deleteUnmatched: true,
      })
    ).toEqual({
      mode: IMPORT_MODE_UPSERT,
      upsert_fields: [1, 3],
      upsert_values: [['a', 'b']],
      delete_unmatched: true,
      allow_ambiguous_matches: false,
    })

    expect(
      buildImportConfiguration({
        mode: IMPORT_MODE_UPDATE,
        upsertFieldIds: [1],
        upsertValues: [['a']],
        allowAmbiguousMatches: true,
      }).allow_ambiguous_matches
    ).toBe(true)
  })
})
