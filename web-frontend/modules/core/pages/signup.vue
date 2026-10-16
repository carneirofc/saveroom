<template>
  <div class="auth__wrapper">
    <EmailNotVerified v-if="displayEmailNotVerified" :email="emailToVerify">
    </EmailNotVerified>
    <template v-if="!displayEmailNotVerified">
      <div class="auth__logo">
        <nuxt-link :to="{ name: 'index' }">
          <Logo />
        </nuxt-link>
      </div>

      <h1 class="auth__head-title">{{ $t('signup.headTitle') }}</h1>
      <div class="auth__head">
        <span class="auth__head-text">
          {{ $t('signup.loginText') }}
          <nuxt-link :to="{ name: 'login' }">
            {{ $t('action.login') }}
          </nuxt-link></span
        >
        <LangPicker />
      </div>
      <template v-if="shouldShowAdminSignupPage">
        <Alert>
          <template #title>{{ $t('signup.requireFirstUser') }}</template>
          <p>{{ $t('signup.requireFirstUserMessage') }}</p></Alert
        >
      </template>
      <template v-if="!isSignupEnabled">
        <Alert type="error">
          <template #title>{{ $t('signup.disabled') }}</template>
          <p>{{ $t('signup.disabledMessage') }}</p></Alert
        >
        <Button tag="nuxt-link" :to="{ name: 'login' }" full-width>
          {{ $t('action.backToLogin') }}</Button
        >
      </template>
      <template v-else>
        <template v-if="loginButtons.length">
          <LoginButtons :hide-if-no-buttons="true" />

          <div class="auth__separator">
            {{ $t('common.or') }}
          </div>
        </template>

        <PasswordRegister v-if="passwordLoginEnabled" @success="next">
        </PasswordRegister>

        <LoginActions v-if="!shouldShowAdminSignupPage"></LoginActions>
      </template>
    </template>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { useStore } from 'vuex'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import PasswordRegister from '@baserow/modules/core/components/auth/PasswordRegister'
import LangPicker from '@baserow/modules/core/components/LangPicker'
import LoginButtons from '@baserow/modules/core/components/auth/LoginButtons'
import LoginActions from '@baserow/modules/core/components/auth/LoginActions'
import EmailNotVerified from '@baserow/modules/core/components/auth/EmailNotVerified.vue'
import { EMAIL_VERIFICATION_OPTIONS } from '@baserow/modules/core/enums'

definePageMeta({
  layout: 'login',
  middleware: ['settings'],
})

const store = useStore()
const router = useRouter()
const { t } = useI18n()
const config = useRuntimeConfig()

// Reactive data
const displayEmailNotVerified = ref(false)
const emailToVerify = ref(null)

await useAsyncData('signup-login-options', async () => {
  // Redirect if already authenticated
  if (store.getters['auth/isAuthenticated']) {
    await navigateTo({ name: 'dashboard' })
    return false
  }
  await store.dispatch('authProvider/fetchLoginOptions')
  return true
})

// Computed properties
const settings = computed(() => store.getters['settings/get'])
const loginActions = computed(
  () => store.getters['authProvider/getAllLoginActions']
)
const loginButtons = computed(
  () => store.getters['authProvider/getAllLoginButtons']
)
const passwordLoginEnabled = computed(
  () => store.getters['authProvider/getPasswordLoginEnabled']
)

const isSignupEnabled = computed(() => {
  if (settings.value.oidc_only) {
    // OIDC-only mode disables self-service signup entirely.
    return false
  }
  return settings.value.allow_new_signups
})

const shouldShowAdminSignupPage = computed(() => {
  return settings.value.show_admin_signup_page
})

// Methods
const next = (params) => {
  if (params?.email) {
    emailToVerify.value = params.email
  }

  if (
    emailToVerify.value &&
    settings.value.email_verification === EMAIL_VERIFICATION_OPTIONS.ENFORCED
  ) {
    displayEmailNotVerified.value = true
  } else {
    router.push({ name: 'dashboard' }).then(() => {
      store.dispatch('settings/hideAdminSignupPage')
    })
  }
}

// Head metadata
useHead({
  title: t('signup.headTitle'),
  link: [
    {
      rel: 'canonical',
      href:
        config.public.publicWebFrontendUrl +
        router.resolve({ name: 'signup' }).href,
    },
  ],
})
</script>
