import { BRANDING_DEFAULTS } from '@baserow/modules/core/brandingDefaults'

/**
 * Applies the runtime branding (see modules/core/server/branding/config.js):
 * the app name in the page title and in the translations, translation
 * overrides, the theme stylesheet with the color/font overrides, and
 * `$branding` for the components that render attribution and documentation
 * links.
 *
 * Translations name the product through the linked message `@:{'app.name'}`,
 * so the app name is written into `app.name` of every locale: a message that
 * falls back to English resolves the link in English.
 *
 * The branding is fetched once during SSR and handed to the client through the
 * payload, so the browser never requests /_branding/config.json itself.
 */
export default defineNuxtPlugin({
  name: 'branding',
  dependsOn: ['i18n'],
  async setup(nuxtApp) {
    const branding = useState('baserow-branding', () => null)

    if (import.meta.server && branding.value === null) {
      try {
        branding.value = await $fetch('/_branding/config.json')
      } catch (error) {
        console.warn('[branding] Could not load the branding config:', error)
        branding.value = {}
      }
    }

    const {
      appName,
      messages,
      version,
      hasTheme,
      siteUrl,
      docsUrl,
      siteTitle,
      showAttribution,
    } = branding.value || {}

    const name = appName || BRANDING_DEFAULTS.appName

    // Resolved here rather than in every component, and never null, so a
    // failed fetch degrades to the built-in links instead of a broken href.
    nuxtApp.provide('branding', {
      appName: name,
      siteUrl: siteUrl || BRANDING_DEFAULTS.siteUrl,
      docsUrl: docsUrl || BRANDING_DEFAULTS.docsUrl,
      siteTitle: siteTitle || appName || BRANDING_DEFAULTS.siteTitle,
      showAttribution: showAttribution ?? BRANDING_DEFAULTS.showAttribution,
    })

    const applyMessages = () => {
      for (const locale of unref(nuxtApp.$i18n.locales)) {
        const code = typeof locale === 'string' ? locale : locale.code
        nuxtApp.$i18n.mergeLocaleMessage(code, { app: { name } })
      }
      if (messages) {
        for (const [locale, localeMessages] of Object.entries(messages)) {
          nuxtApp.$i18n.mergeLocaleMessage(locale, localeMessages)
        }
      }
    }
    applyMessages()
    // Switching language lazy loads that locale's files, which bring their
    // own values for any key they define and would replace the overrides.
    watch(nuxtApp.$i18n.locale, applyMessages)

    const link = []
    if (hasTheme) {
      link.push({
        rel: 'stylesheet',
        href: `/_branding/theme.css?v=${version}`,
        key: 'baserow-branding-theme',
        // Render after the bundled stylesheets so the overrides win.
        tagPriority: 'low',
      })
    }

    useHead({
      title: name,
      titleTemplate: (title) =>
        title && title !== name ? `${title} | ${name}` : name,
      link,
    })
  },
})
