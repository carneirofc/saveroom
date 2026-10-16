import { defineEventHandler, setResponseHeaders } from 'h3'

import { loadBranding } from './config.js'

/**
 * GET /_branding/config.json — the branding values the Vue app needs at
 * runtime (title, translations, whether a theme stylesheet exists). Read during
 * SSR by the branding plugin and shipped to the client in the payload.
 */
export default defineEventHandler(async (event) => {
  const {
    appName,
    messages,
    version,
    hasTheme,
    siteUrl,
    docsUrl,
    siteTitle,
    showAttribution,
  } = await loadBranding()
  setResponseHeaders(event, { 'Cache-Control': 'no-cache' })
  return {
    appName,
    messages,
    version,
    hasTheme,
    siteUrl,
    docsUrl,
    siteTitle,
    showAttribution,
  }
})
