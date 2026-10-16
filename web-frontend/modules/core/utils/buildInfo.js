import moment from '@baserow/modules/core/moment'

/**
 * Build metadata identifies the exact source a running instance was built from.
 * It is injected as docker build args when an image is published, so every value
 * is empty in a development checkout and each helper here has to stay readable
 * with nothing, part, or all of it present.
 */

export const SHORT_COMMIT_LENGTH = 8

/**
 * Shortens a commit hash to the length humans actually compare, leaving a
 * shorter hash untouched.
 */
export function shortCommit(commit) {
  if (!commit) {
    return ''
  }
  return String(commit).slice(0, SHORT_COMMIT_LENGTH)
}

/**
 * Formats an ISO 8601 build timestamp in the viewer's own timezone, following
 * the same convention as the other dates in the interface.
 */
export function formatBuildDate(buildDate) {
  if (!buildDate) {
    return ''
  }
  const parsed = moment.utc(buildDate)
  return parsed.isValid() ? parsed.local().format('L LT') : ''
}

/**
 * The one line version of a build: the release tag next to the short commit.
 * Falls back to whichever of the two exists, and to an empty string when the
 * instance is a development build, so a caller can hide the element entirely.
 */
export function buildLabel(buildInfo) {
  const version = buildInfo?.version || ''
  const commit = shortCommit(buildInfo?.commit)
  return [version, commit].filter((part) => part !== '').join(' · ')
}

/**
 * The expanded version, for a title attribute: the full commit hash and the
 * build date, which are too long to show inline.
 */
export function buildTitle(buildInfo) {
  const version = buildInfo?.version || ''
  const commit = buildInfo?.commit || ''
  const buildDate = formatBuildDate(
    buildInfo?.buildDate || buildInfo?.build_date
  )
  return [version, commit, buildDate].filter((part) => part !== '').join('\n')
}

/**
 * Whether two builds came from the same commit. A backend and a web-frontend
 * that disagree mean half of a deployment was upgraded, which is worth telling
 * an admin about. Builds are only comparable when both report a commit.
 */
export function isSameBuild(a, b) {
  const commitA = a?.commit || ''
  const commitB = b?.commit || ''
  if (commitA === '' || commitB === '') {
    return true
  }
  return commitA === commitB
}
