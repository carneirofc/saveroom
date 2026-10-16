import { shallowMount } from '@vue/test-utils'

import ExternalLinkBaserowLogo from '@baserow/modules/core/components/ExternalLinkBaserowLogo'
import FormViewPoweredBy from '@baserow/modules/database/components/view/form/FormViewPoweredBy'

// The runtime branding plugin resolves these before any component renders, so
// the components only ever see fully populated values.
const branding = (overrides = {}) => ({
  siteUrl: 'https://acme.example',
  docsUrl: 'https://docs.acme.example',
  appName: 'Acme Data',
  siteTitle: 'Acme Data',
  showAttribution: true,
  ...overrides,
})

const mount = (component, brandingOverrides) =>
  shallowMount(component, {
    global: {
      mocks: {
        $branding: branding(brandingOverrides),
        $t: (key) => key,
      },
      // Logo is registered globally by Nuxt, so it has to be stubbed here.
      stubs: {
        Logo: { props: ['alt'], template: '<img :alt="alt" />' },
      },
    },
  })

describe.each([
  ['ExternalLinkBaserowLogo', ExternalLinkBaserowLogo],
  ['FormViewPoweredBy', FormViewPoweredBy],
])('%s', (name, component) => {
  it('links to the branded site with the branded title', () => {
    const link = mount(component).find('a')
    expect(link.attributes('href')).toBe('https://acme.example')
    expect(link.attributes('title')).toBe('Acme Data')
  })

  it('passes the branded title to the logo as alt text', () => {
    expect(mount(component).find('img').attributes('alt')).toBe('Acme Data')
  })

  it('renders nothing when attribution is switched off', () => {
    const wrapper = mount(component, { showAttribution: false })
    expect(wrapper.find('a').exists()).toBe(false)
    expect(wrapper.html()).toBe('<!--v-if-->')
  })
})
