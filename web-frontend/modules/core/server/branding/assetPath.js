import path from 'node:path'

export const BRANDING_ASSETS_PREFIX = '/_branding/assets/'

const CONTENT_TYPES = {
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.webp': 'image/webp',
  '.gif': 'image/gif',
  '.ico': 'image/x-icon',
  '.woff': 'font/woff',
  '.woff2': 'font/woff2',
  '.ttf': 'font/ttf',
  '.otf': 'font/otf',
}

// Folders with built-in defaults bundled as Nitro server assets (registered in
// modules/core/module.js). `files/` has no defaults: it only serves what the
// operator puts in the branding directory, e.g. fonts used by theme.css.
export const DEFAULT_ASSET_STORAGE = {
  img: 'assets:branding-img',
  icons: 'assets:branding-icons',
}
const ROOTS = new Set([...Object.keys(DEFAULT_ASSET_STORAGE), 'files'])
const SEGMENT = /^[\w-][\w.-]*$/

/**
 * Validates a `/_branding/assets/...` request path and returns its parts, or
 * null when it is not something the assets handler may serve. Only allow-listed
 * file types in known folders, with plain path segments: no dot-files, `..`,
 * encoded separators or empty segments.
 */
export function parseAssetPath(requestPath) {
  const pathname = requestPath.split('?')[0]
  if (!pathname.startsWith(BRANDING_ASSETS_PREFIX)) {
    return null
  }
  let relative
  try {
    relative = decodeURIComponent(pathname.slice(BRANDING_ASSETS_PREFIX.length))
  } catch {
    return null
  }
  const segments = relative.split('/')
  const [root, ...rest] = segments
  if (
    !ROOTS.has(root) ||
    rest.length === 0 ||
    !segments.every((segment) => SEGMENT.test(segment))
  ) {
    return null
  }
  const contentType = CONTENT_TYPES[path.extname(relative).toLowerCase()]
  if (!contentType) {
    return null
  }
  return { root, relative, rest: rest.join('/'), contentType }
}

/**
 * Resolves `relative` inside `dir`, or null if it would escape it. Defence in
 * depth on top of parseAssetPath.
 */
export function resolveInside(dir, relative) {
  const root = path.resolve(dir)
  const file = path.resolve(root, relative)
  return file.startsWith(root + path.sep) ? file : null
}
