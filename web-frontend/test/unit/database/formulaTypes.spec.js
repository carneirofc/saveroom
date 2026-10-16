import {
  BaserowFormulaURLType,
  BaserowFormulaLinkType,
} from '@baserow/modules/database/formula/formulaTypes'

describe('formula URL types toHumanReadableString', () => {
  const app = {}
  const field = {}

  describe.each([
    ['BaserowFormulaURLType', new BaserowFormulaURLType({ app })],
    ['BaserowFormulaLinkType', new BaserowFormulaLinkType({ app })],
  ])('%s', (name, formulaType) => {
    test('returns an empty string for a null value', () => {
      expect(formulaType.toHumanReadableString(field, null)).toBe('')
    })

    test('returns an empty string for an undefined value', () => {
      expect(formulaType.toHumanReadableString(field, undefined)).toBe('')
    })

    test('formats a value with a label and url', () => {
      expect(
        formulaType.toHumanReadableString(field, {
          label: 'Baserow',
          url: 'https://example.com',
        })
      ).toBe('Baserow (https://example.com)')
    })

    test('returns the url when there is no label', () => {
      expect(
        formulaType.toHumanReadableString(field, {
          url: 'https://example.com',
        })
      ).toBe('https://example.com')
    })
  })

  test('BaserowFormulaURLType returns a plain string value as-is', () => {
    const formulaType = new BaserowFormulaURLType({ app })
    expect(
      formulaType.toHumanReadableString(field, 'https://example.com')
    ).toBe('https://example.com')
  })
})
