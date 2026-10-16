import { shallowMount } from '@vue/test-utils'
import OIDCLoginButton from '@baserow/modules/core/components/auth/OIDCLoginButton.vue'

function mountButton(props = {}, query = {}) {
  return shallowMount(OIDCLoginButton, {
    props: {
      redirectUrl: 'http://localhost:8000/api/sso/oidc/login/keycloak/',
      name: 'Keycloak',
      icon: '/icon.svg',
      ...props,
    },
    global: {
      mocks: {
        $t: (key) => key,
        $route: { query },
      },
      stubs: { Button: { template: '<a><slot /></a>' } },
    },
  })
}

describe('OIDCLoginButton.vue', () => {
  it('uses the redirect url as-is', () => {
    const wrapper = mountButton()
    expect(wrapper.vm.loginUrl).toBe(
      'http://localhost:8000/api/sso/oidc/login/keycloak/'
    )
  })

  it('renders the provider name when not small', () => {
    const wrapper = mountButton({ small: false })
    expect(wrapper.text()).toContain('Keycloak')
  })

  it('hides the provider name label when small', () => {
    const wrapper = mountButton({ small: true })
    expect(wrapper.text()).not.toContain('Keycloak')
  })
})
