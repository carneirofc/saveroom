import { createHash } from 'node:crypto'
import { readFile, stat } from 'node:fs/promises'

import {
  defineEventHandler,
  handleCacheHeaders,
  setResponseHeaders,
  setResponseStatus,
} from 'h3'
import { useStorage } from 'nitropack/runtime'

import {
  DEFAULT_ASSET_STORAGE,
  parseAssetPath,
  resolveInside,
} from './assetPath.js'
import { loadBranding } from './config.js'

// Overrides are picked up within this window; the ETag makes revalidation cheap.
// handleCacheHeaders adds `public` itself.
const MAX_AGE_SECONDS = 60

// A plain 404: a thrown h3 error would render the full Nuxt error page.
function notFound(event) {
  setResponseStatus(event, 404)
  setResponseHeaders(event, { 'Content-Type': 'text/plain; charset=utf-8' })
  return 'Not found'
}

async function readOverride(dir, relative) {
  const file = resolveInside(dir, relative)
  if (!file) {
    return null
  }
  try {
    const info = await stat(file)
    if (!info.isFile()) {
      return null
    }
    return {
      body: await readFile(file),
      etag: `"${info.size.toString(16)}-${Math.floor(info.mtimeMs).toString(16)}"`,
    }
  } catch (error) {
    if (error.code === 'ENOENT' || error.code === 'ENOTDIR') {
      return null
    }
    throw error
  }
}

async function readDefault(root, rest) {
  const storage = DEFAULT_ASSET_STORAGE[root]
  if (!storage) {
    return null
  }
  const raw = await useStorage(storage).getItemRaw(rest)
  if (!raw) {
    return null
  }
  const body = Buffer.isBuffer(raw) ? raw : Buffer.from(raw)
  return {
    body,
    etag: `"${createHash('sha1').update(body).digest('hex').slice(0, 16)}"`,
  }
}

/**
 * GET /_branding/assets/{img,icons,files}/... — serves a file from the
 * branding directory when present, otherwise the built-in default.
 */
export default defineEventHandler(async (event) => {
  const asset = parseAssetPath(event.path)
  if (!asset) {
    return notFound(event)
  }

  const { dir } = await loadBranding()
  const found =
    (await readOverride(dir, asset.relative)) ||
    (await readDefault(asset.root, asset.rest))
  if (!found) {
    return notFound(event)
  }

  const headers = {
    'Content-Type': asset.contentType,
    'X-Content-Type-Options': 'nosniff',
  }
  if (asset.contentType === 'image/svg+xml') {
    // An SVG opened directly must not be able to run script.
    headers['Content-Security-Policy'] =
      "default-src 'none'; style-src 'unsafe-inline'; sandbox"
  }
  setResponseHeaders(event, headers)
  if (
    handleCacheHeaders(event, {
      etag: found.etag,
      maxAge: MAX_AGE_SECONDS,
      cacheControls: ['must-revalidate'],
    })
  ) {
    return null
  }
  return found.body
})
