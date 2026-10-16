import { shallowMount } from '@vue/test-utils'

import BuildInfo from '@baserow/modules/core/components/version/BuildInfo.vue'
import { PROJECT_CREDITS } from '@baserow/modules/core/brandingDefaults'

const COMMIT = '8b38f7dc832a689794023a21ee21e01772ec28de'

const backendBuild = (overrides = {}) => ({
  version: 'v0.13.0',
  commit: COMMIT,
  build_date: '2026-09-18T10:34:30Z',
  baserow_version: '2.3.2',
  ...overrides,
})

const mount = (
  backend,
  frontend = { version: 'v0.13.0', commit: COMMIT },
  props = {},
  branding = { showAttribution: true }
) =>
  shallowMount(BuildInfo, {
    props: { backend, ...props },
    global: {
      mocks: {
        $buildInfo: { buildDate: '', ...frontend },
        $branding: branding,
        $t: (key, values) =>
          values ? `${key}:${JSON.stringify(values)}` : key,
      },
      stubs: {
        Copied: true,
        Alert: { template: '<div class="alert"><slot /></div>' },
      },
    },
  })

describe('BuildInfo', () => {
  it('lists the backend version, commit and build date', () => {
    const rows = mount(backendBuild()).findAll('.build-info__row')
    expect(rows).toHaveLength(4)
    expect(rows[0].text()).toContain('v0.13.0')
    // The commit is shortened to what humans actually compare.
    expect(rows[1].text()).toContain('8b38f7dc')
    expect(rows[1].text()).not.toContain(COMMIT)
    expect(rows[3].text()).toContain('2.3.2')
  })

  it('keeps the full commit available to copy', () => {
    const value = mount(backendBuild()).findAll('.build-info__value-text')[1]
    expect(value.attributes('title')).toBe(COMMIT)
  })

  it('drops the commit and build date rows for a development build', () => {
    const wrapper = mount(
      backendBuild({ version: '', commit: '', build_date: '' }),
      { version: '', commit: '' }
    )
    const rows = wrapper.findAll('.build-info__row')
    expect(rows).toHaveLength(2)
    expect(rows[0].text()).toContain('buildInfo.developmentBuild')
    expect(wrapper.find('.build-info__frontend').exists()).toBe(false)
  })

  it('warns when the backend and the web-frontend are different builds', () => {
    const wrapper = mount(backendBuild(), {
      version: 'v0.12.0',
      commit: 'abc1234def',
    })
    expect(wrapper.find('.build-info__mismatch').exists()).toBe(true)
  })

  it('stays quiet when both halves are the same build', () => {
    const wrapper = mount(backendBuild())
    expect(wrapper.find('.build-info__mismatch').exists()).toBe(false)
  })

  it('renders no rows while the backend build is still loading', () => {
    const wrapper = mount(null)
    expect(wrapper.findAll('.build-info__row')).toHaveLength(0)
    expect(wrapper.find('.build-info__mismatch').exists()).toBe(false)
    expect(wrapper.find('.build-info__unavailable').exists()).toBe(false)
  })

  // A backend older than this web-frontend has no endpoint to answer, so the
  // failure has to be stated rather than left as an empty panel.
  it('states that the backend build could not be read', () => {
    const wrapper = mount(null, undefined, { error: true })
    expect(wrapper.find('.build-info__unavailable').exists()).toBe(true)
    expect(wrapper.findAll('.build-info__row')).toHaveLength(0)
    // The web-frontend half still reports itself.
    expect(wrapper.find('.build-info__frontend').text()).toContain('v0.13.0')
  })

  it('credits the fork and upstream Baserow', () => {
    const credits = mount(backendBuild()).find('.build-info__credits')
    const hrefs = credits.findAll('a').map((link) => link.attributes('href'))
    expect(hrefs).toEqual([
      PROJECT_CREDITS.forkUrl,
      PROJECT_CREDITS.upstreamUrl,
      PROJECT_CREDITS.licenseUrl,
    ])
  })

  it('keeps the credits when the backend build could not be read', () => {
    const wrapper = mount(null, undefined, { error: true })
    expect(wrapper.find('.build-info__credits').exists()).toBe(true)
  })

  it('hides the credits when the branding turns attribution off', () => {
    const wrapper = mount(
      backendBuild(),
      undefined,
      {},
      {
        showAttribution: false,
      }
    )
    expect(wrapper.find('.build-info__credits').exists()).toBe(false)
  })
})
