<template>
  <div class="auth__wrapper">
    <Login
      :display-header="true"
      :redirect-on-success="true"
      :redirect-by-default="redirectByDefault"
      :sso-error="ssoError"
    />
  </div>
</template>

<script setup>
import Login from '@baserow/modules/core/components/auth/Login'

definePageMeta({
  name: 'login',
  layout: 'login',
  middleware: ['settings'],
})

const { $store: store } = useNuxtApp()

const route = useRoute()
const i18n = useI18n()
const config = useRuntimeConfig()
const router = useRouter()

// Redirect logic
if (store.getters['settings/get'].show_admin_signup_page === true) {
  await navigateTo({ name: 'signup' })
} else if (store.getters['auth/isAuthenticated']) {
  await navigateTo({ name: 'dashboard' })
}

await useAsyncData('loginData', async () => {
  // Fetch login options (will populate Vuex store)
  await store.dispatch('authProvider/fetchLoginOptions')
  return true
})

// Head
useHead({
  title: i18n.t('login.title'),
  link: [
    {
      rel: 'canonical',
      href:
        config.public.publicWebFrontendUrl +
        router.resolve({ name: 'login' }).href,
    },
  ],
})

const ssoError = computed(() => route.query.error || null)

const redirectByDefault = computed(() => {
  // Never auto-redirect back into a provider that just failed, otherwise the user
  // would be bounced straight back into the failing flow.
  return !(route.query.noredirect === null) && !ssoError.value
})
</script>
