import { TestApp } from '@baserow/test/helpers/testApp'

describe('authProvider store', () => {
  let testApp = null
  let store = null

  beforeEach(() => {
    testApp = new TestApp()
    store = testApp.store
  })

  afterEach(() => {
    testApp.afterEach()
  })

  const oidcLoginOptions = {
    password: { type: 'password' },
    openid_connect: {
      type: 'openid_connect',
      items: [
        {
          type: 'openid_connect',
          name: 'Keycloak',
          redirect_url: 'http://localhost:8000/api/sso/oidc/login/keycloak/',
        },
      ],
      default_redirect_url:
        'http://localhost:8000/api/sso/oidc/login/keycloak/',
    },
  }

  test('fetchLoginOptions exposes an OIDC login button', async () => {
    testApp.mock
      .onGet('/auth-provider/login-options/')
      .reply(200, oidcLoginOptions)

    await store.dispatch('authProvider/fetchLoginOptions')

    const buttons = store.getters['authProvider/getAllLoginButtons']
    expect(buttons).toHaveLength(1)
    expect(buttons[0]).toMatchObject({
      type: 'openid_connect',
      name: 'Keycloak',
      redirect_url: 'http://localhost:8000/api/sso/oidc/login/keycloak/',
    })
    expect(store.getters['authProvider/getPasswordLoginEnabled']).toBe(true)
  })

  test('a single OIDC provider yields no default redirect while password is enabled', async () => {
    testApp.mock
      .onGet('/auth-provider/login-options/')
      .reply(200, oidcLoginOptions)

    await store.dispatch('authProvider/fetchLoginOptions')

    // Two options (password + openid_connect) => never auto-redirect.
    expect(store.getters['authProvider/getDefaultRedirectUrl']).toBe(null)
  })

  test('OIDC is the only option => auto-redirect to the provider', async () => {
    testApp.mock.onGet('/auth-provider/login-options/').reply(200, {
      openid_connect: oidcLoginOptions.openid_connect,
    })

    await store.dispatch('authProvider/fetchLoginOptions')

    expect(store.getters['authProvider/getDefaultRedirectUrl']).toBe(
      'http://localhost:8000/api/sso/oidc/login/keycloak/'
    )
  })

  test('multiple OIDC providers each render a button', async () => {
    testApp.mock.onGet('/auth-provider/login-options/').reply(200, {
      openid_connect: {
        type: 'openid_connect',
        items: [
          {
            type: 'openid_connect',
            name: 'Keycloak',
            redirect_url: 'http://localhost:8000/api/sso/oidc/login/keycloak/',
          },
          {
            type: 'openid_connect',
            name: 'Google',
            redirect_url: 'http://localhost:8000/api/sso/oidc/login/google/',
          },
        ],
        default_redirect_url: null,
      },
    })

    await store.dispatch('authProvider/fetchLoginOptions')

    const buttons = store.getters['authProvider/getAllLoginButtons']
    expect(buttons.map((b) => b.name)).toEqual(['Keycloak', 'Google'])
    expect(store.getters['authProvider/getDefaultRedirectUrl']).toBe(null)
  })
})
