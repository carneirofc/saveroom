import {
  defineNuxtModule,
  addPlugin,
  createResolver,
  addRouteMiddleware,
  extendPages,
} from 'nuxt/kit'
import { routes } from './routes'
import { locales } from '../../config/locales.js'

export default defineNuxtModule({
  meta: {
    name: '@baserow/dashboard',
    configKey: 'dashboard',
  },
  async setup(options, nuxt) {
    const { resolve } = createResolver(import.meta.url)

    addPlugin(resolve('./plugin.js'))
    addPlugin(resolve('./plugins/realtime.js'))

    addRouteMiddleware({
      name: 'dashboardLoading',
      path: resolve('./middleware/dashboardLoading.js'),
      global: false,
    })

    extendPages((pages) => {
      pages.push(...routes)
    })

    nuxt.hook('i18n:registerModule', (register) => {
      register({
        langDir: resolve('./locales'),
        locales,
      })
    })
  },
})
