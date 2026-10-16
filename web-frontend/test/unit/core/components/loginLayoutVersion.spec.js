import { shallowMount } from '@vue/test-utils'

import LoginLayout from '@baserow/modules/core/layouts/login.vue'

const COMMIT = '8b38f7dc832a689794023a21ee21e01772ec28de'

const mount = (buildInfo) =>
  shallowMount(LoginLayout, {
    global: {
      mocks: { $buildInfo: buildInfo },
      stubs: { Toasts: true },
    },
  })

describe('login layout version footer', () => {
  it('states the build every login page is served from', () => {
    const footer = mount({
      version: 'v0.13.0',
      commit: COMMIT,
      buildDate: '2026-09-18T10:34:30Z',
    }).find('.auth__version')

    expect(footer.text()).toBe('v0.13.0 · 8b38f7dc')
    // The full hash is too long to show inline, so it lives in the title.
    expect(footer.attributes('title')).toContain(COMMIT)
  })

  it('renders nothing for a development build', () => {
    const wrapper = mount({ version: '', commit: '', buildDate: '' })
    expect(wrapper.find('.auth__version').exists()).toBe(false)
  })
})
