// @vitest-environment node
import { readdir, readFile } from 'node:fs/promises'
import path from 'node:path'

import { BRANDING_DEFAULTS } from '@baserow/modules/core/brandingDefaults'

const root = path.resolve(__dirname, '../../../..')

const localeFiles = async () => {
  const dirs = [path.join(root, 'locales')]
  for (const module of await readdir(path.join(root, 'modules'))) {
    dirs.push(path.join(root, 'modules', module, 'locales'))
  }
  const files = []
  for (const dir of dirs) {
    const names = await readdir(dir).catch(() => [])
    files.push(
      ...names.filter((n) => n.endsWith('.json')).map((n) => path.join(dir, n))
    )
  }
  return files
}

const strings = (value, prefix = '') =>
  typeof value === 'string'
    ? [[prefix, value]]
    : Object.entries(value).flatMap(([key, child]) =>
        strings(child, prefix ? `${prefix}.${key}` : key)
      )

describe('app name in translations', () => {
  test('the default name matches the translation fallback', async () => {
    const en = JSON.parse(
      await readFile(path.join(root, 'modules/core/locales/en.json'), 'utf8')
    )
    expect(en.app.name).toBe(BRANDING_DEFAULTS.appName)
  })

  test('linked messages use the brace form', async () => {
    // A bare `@:app.name` swallows trailing punctuation into the key, so
    // "Welcome to @:app.name!" looks up `app.name!` and renders the raw key.
    const offenders = []
    for (const file of await localeFiles()) {
      const messages = JSON.parse(await readFile(file, 'utf8'))
      for (const [key, value] of strings(messages)) {
        if (/@[.a-z]*:(?!\{')/.test(value)) {
          offenders.push(`${path.relative(root, file)}: ${key}`)
        }
      }
    }
    expect(offenders).toEqual([])
  })
})
