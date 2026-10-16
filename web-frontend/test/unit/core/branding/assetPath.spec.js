// @vitest-environment node
import path from 'node:path'

import {
  parseAssetPath,
  resolveInside,
} from '@baserow/modules/core/server/branding/assetPath'

describe('parseAssetPath', () => {
  test.each([
    ['/_branding/assets/img/logo.svg', 'img', 'logo.svg', 'image/svg+xml'],
    [
      '/_branding/assets/icons/formula.svg?v=1',
      'icons',
      'formula.svg',
      'image/svg+xml',
    ],
    [
      '/_branding/assets/files/fonts/Brand-Regular.woff2',
      'files',
      'fonts/Brand-Regular.woff2',
      'font/woff2',
    ],
    [
      '/_branding/assets/img/favicon_16.PNG',
      'img',
      'favicon_16.PNG',
      'image/png',
    ],
  ])('accepts %s', (requestPath, root, rest, contentType) => {
    expect(parseAssetPath(requestPath)).toMatchObject({
      root,
      rest,
      contentType,
    })
  })

  test.each([
    '/_branding/assets/img/../../../etc/passwd.png',
    '/_branding/assets/img/%2e%2e/%2e%2e/secret.png',
    '/_branding/assets/img/..%2fsecret.png',
    '/_branding/assets/img/.hidden.svg',
    '/_branding/assets/img//logo.svg',
    '/_branding/assets/img/logo.html',
    '/_branding/assets/img/logo',
    '/_branding/assets/branding.json',
    '/_branding/assets/theme.css',
    '/_branding/assets/other/logo.svg',
    '/_branding/assets/img',
    '/_branding/assets/img/%E0%A4%A.svg',
    '/img/logo.svg',
  ])('rejects %s', (requestPath) => {
    expect(parseAssetPath(requestPath)).toBeNull()
  })
})

// The server runs on Linux, but the suite also has to pass on a Windows
// checkout, where `path.resolve` prefixes a drive letter and joins with
// backslashes. Build the expected path with `path` rather than writing a POSIX
// literal, so the assertion is about the resolution and not the separator.
describe('resolveInside', () => {
  test('resolves paths inside the directory', () => {
    const dir = path.resolve('/baserow/branding')
    expect(resolveInside('/baserow/branding', 'img/logo.svg')).toBe(
      path.join(dir, 'img', 'logo.svg')
    )
  })

  test('refuses paths escaping the directory', () => {
    expect(resolveInside('/baserow/branding', '../etc/passwd')).toBeNull()
    expect(resolveInside('/baserow/branding', '/etc/passwd')).toBeNull()
    expect(resolveInside('/baserow/branding', '')).toBeNull()
  })
})
