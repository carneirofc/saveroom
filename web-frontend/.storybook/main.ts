import type { StorybookConfig } from '@nuxtjs/storybook'
import { mergeConfig } from 'vite'
import { fileURLToPath } from 'node:url'

const config: StorybookConfig = {
  previewAnnotations: (entries = []) => [
    fileURLToPath(new URL('./runtime-config.js', import.meta.url)),
    ...entries,
  ],
  stories: [
    '../stories/**/*.mdx',
    '../stories/**/*.stories.@(js|jsx|mjs|ts|tsx)',
  ],
  addons: [
    '@storybook/addon-links',
    '@storybook/addon-docs',
    '@storybook/addon-designs',
  ],
  framework: {
    name: '@storybook-vue/nuxt',
    options: {},
  },
  docs: {
    autodocs: 'tag',
  },
  /** Limit 504 "Outdated Optimize Dep" on cold start: wait for dep crawl, pre-bundle common deps. */
  async viteFinal(viteConfig) {
    return mergeConfig(viteConfig, {
      optimizeDeps: {
        holdUntilCrawlEnd: true,
        include: [
          'axios',
          'lodash',
          'lodash-es',
          'mitt',
          'papaparse',
          'flush-promises',
          'vuex',
          'moment',
        ],
      },
    })
  },
}
export default config
