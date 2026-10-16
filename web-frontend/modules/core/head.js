import { BRANDING_DEFAULTS } from './brandingDefaults.js'

export default {
  title: BRANDING_DEFAULTS.appName,
  titleTemplate: `%s | ${BRANDING_DEFAULTS.appName}`,
  meta: [
    { charset: 'utf-8' },
    {
      name: 'viewport',
      content:
        'width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no',
    },
    {
      name: 'format-detection',
      content: 'telephone=no, email=no, address=no, date=no',
    },
  ],
  // The `key` on each favicon is what allows other parts of the app (e.g. the
  // application builder's custom favicon) to override these defaults. unhead
  // dedupes `link` tags by `key`.
  link: [
    {
      rel: 'icon',
      type: 'image/png',
      href: '/_branding/assets/img/favicon_16.png',
      sizes: '16x16',
      key: 'favicon-16',
    },
    {
      rel: 'icon',
      type: 'image/png',
      href: '/_branding/assets/img/favicon_32.png',
      sizes: '32x32',
      key: 'favicon-32',
    },
    {
      rel: 'icon',
      type: 'image/png',
      href: '/_branding/assets/img/favicon_48.png',
      sizes: '64x64',
      key: 'favicon-64',
    },
    {
      rel: 'icon',
      type: 'image/png',
      href: '/_branding/assets/img/favicon_192.png',
      sizes: '192x192',
      key: 'favicon-192',
    },
  ],
}
