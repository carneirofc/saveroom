import {
  buildLabel,
  buildTitle,
  formatBuildDate,
  isSameBuild,
  shortCommit,
} from '@baserow/modules/core/utils/buildInfo'

describe('test build info utils', () => {
  const commit = '8b38f7dc832a689794023a21ee21e01772ec28de'

  describe('shortCommit', () => {
    test('shortens a full hash to the part humans compare', () => {
      expect(shortCommit(commit)).toBe('8b38f7dc')
    })

    test('leaves an already short hash alone', () => {
      expect(shortCommit('8b38f7d')).toBe('8b38f7d')
    })

    test('returns an empty string when there is no commit', () => {
      expect(shortCommit('')).toBe('')
      expect(shortCommit(undefined)).toBe('')
      expect(shortCommit(null)).toBe('')
    })
  })

  describe('formatBuildDate', () => {
    test('returns an empty string for a missing or unparseable date', () => {
      expect(formatBuildDate('')).toBe('')
      expect(formatBuildDate(undefined)).toBe('')
      expect(formatBuildDate('not a date')).toBe('')
    })

    test('formats a valid timestamp', () => {
      // The exact string depends on the machine's timezone and locale, so only
      // assert that something was rendered.
      expect(formatBuildDate('2026-09-18T10:34:30Z')).not.toBe('')
    })
  })

  describe('buildLabel', () => {
    test('joins the version and the short commit', () => {
      expect(buildLabel({ version: 'v0.13.0', commit })).toBe(
        'v0.13.0 · 8b38f7dc'
      )
    })

    test('falls back to whichever part exists', () => {
      expect(buildLabel({ version: 'v0.13.0', commit: '' })).toBe('v0.13.0')
      expect(buildLabel({ version: '', commit })).toBe('8b38f7dc')
    })

    test('is empty for a development build', () => {
      expect(buildLabel({ version: '', commit: '', buildDate: '' })).toBe('')
      expect(buildLabel(null)).toBe('')
      expect(buildLabel(undefined)).toBe('')
    })
  })

  describe('buildTitle', () => {
    test('expands to the full commit and the build date', () => {
      const title = buildTitle({
        version: 'v0.13.0',
        commit,
        buildDate: '2026-09-18T10:34:30Z',
      })
      expect(title).toContain('v0.13.0')
      expect(title).toContain(commit)
      expect(title.split('\n')).toHaveLength(3)
    })

    test('accepts the snake case build date the API returns', () => {
      const title = buildTitle({
        version: 'v0.13.0',
        commit: '',
        build_date: '2026-09-18T10:34:30Z',
      })
      expect(title.split('\n')).toHaveLength(2)
    })

    test('is empty for a development build', () => {
      expect(buildTitle({ version: '', commit: '', buildDate: '' })).toBe('')
      expect(buildTitle(null)).toBe('')
    })
  })

  describe('isSameBuild', () => {
    test('compares the commits', () => {
      expect(isSameBuild({ commit }, { commit })).toBe(true)
      expect(isSameBuild({ commit }, { commit: 'abc1234' })).toBe(false)
    })

    test('treats a missing commit as not comparable', () => {
      expect(isSameBuild({ commit: '' }, { commit })).toBe(true)
      expect(isSameBuild({ commit }, { commit: '' })).toBe(true)
      expect(isSameBuild(null, null)).toBe(true)
    })
  })
})
