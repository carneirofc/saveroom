import { defineEventHandler, handleCacheHeaders, setResponseHeaders } from 'h3'

import { loadBranding } from './config.js'

/**
 * GET /_branding/theme.css — the runtime color/font overrides plus the
 * operator's theme.css. Revalidated on every load (ETag) so edits to the
 * branding directory show up on the next page refresh.
 */
export default defineEventHandler(async (event) => {
  const branding = await loadBranding()
  setResponseHeaders(event, {
    'Content-Type': 'text/css; charset=utf-8',
    'X-Content-Type-Options': 'nosniff',
  })
  if (
    handleCacheHeaders(event, {
      etag: `"${branding.version}"`,
      cacheControls: ['no-cache'],
    })
  ) {
    return null
  }
  return branding.themeCss
})
