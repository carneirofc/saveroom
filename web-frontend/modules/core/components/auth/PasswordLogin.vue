<template>
  <div>
    <Error :error="error"></Error>
    <form @submit.prevent="login">
      <FormGroup
        class="mb-24"
        required
        small-label
        :label="$t('field.emailAddress')"
        :error="fieldHasErrors('email')"
      >
        <FormInput
          ref="email"
          v-model="values.email"
          type="email"
          size="large"
          :error="fieldHasErrors('email')"
          :placeholder="$t('login.emailPlaceholder')"
          autocomplete="username"
          @blur="v$.values.email.$touch"
        />

        <template #error>
          <i class="iconoir-warning-triangle"></i>
          {{ $t('error.invalidEmail') }}
        </template>
      </FormGroup>

      <FormGroup
        class="mb-32"
        required
        small-label
        :label="$t('field.password')"
        :error="fieldHasErrors('password')"
      >
        <template v-if="displayForgotPassword" #after-label>
          <nuxt-link tabindex="3" :to="{ name: 'forgot-password' }">
            {{ $t('login.forgotPassword') }}
          </nuxt-link>
        </template>
        <FormInput
          ref="password"
          v-model="values.password"
          type="password"
          size="large"
          :error="fieldHasErrors('password')"
          :placeholder="$t('login.passwordPlaceholder')"
          autocomplete="current-password"
          @blur="v$.values.password.$touch"
        />
        <template #error>
          <i class="iconoir-warning-triangle"></i>
          {{ $t('error.passwordRequired') }}
        </template>
      </FormGroup>

      <div class="auth__action mb-32">
        <Button
          type="primary"
          size="large"
          :loading="loading"
          full-width
          :disabled="loading"
        >
          {{ $t('action.login') }}
        </Button>
      </div>
    </form>
  </div>
</template>

<script>
import { useVuelidate } from '@vuelidate/core'
import { reactive } from 'vue'
import { required, email } from '@vuelidate/validators'
import form from '@baserow/modules/core/mixins/form'
import error from '@baserow/modules/core/mixins/error'

export default {
  name: 'PasswordLogin',
  mixins: [error],
  props: {
    displayForgotPassword: {
      type: Boolean,
      required: false,
      default: true,
    },
  },
  emits: ['email-not-verified', 'success', 'two-factor-auth'],
  setup() {
    const values = reactive({
      values: {
        email: '',
        password: '',
      },
    })

    const rules = {
      values: {
        email: { required, email },
        password: { required },
      },
    }

    return {
      values: values.values,
      v$: useVuelidate(rules, values, { $lazy: true }),
    }
  },
  data() {
    return {
      loading: false,
    }
  },
  async mounted() {
    if (!this.$config.public.baserowDisablePublicUrlCheck) {
      const publicBackendUrl = new URL(this.$config.public.publicBackendUrl)
      if (publicBackendUrl.hostname !== window.location.hostname) {
        // If the host of the browser location does not match the PUBLIC_BACKEND_URL
        // then we are probably mis-configured.
        try {
          // Attempt to connect to the backend using the configured PUBLIC_BACKEND_URL
          // just in-case it is actually configured correctly.
          await this.$client.get('_health/')
        } catch (error) {
          const publicBackendUrlWithProto =
            publicBackendUrl.protocol + '//' + publicBackendUrl.host
          const browserWindowUrl = location.protocol + '//' + location.host
          this.showError(
            'Backend URL mis-configuration detected',
            `Cannot connect to the backend at ${publicBackendUrlWithProto}.` +
              ` You visited ${this.$branding.appName} at ${browserWindowUrl} ` +
              ' which indicates you have mis-configured the' +
              ' BASEROW_PUBLIC_URL or PUBLIC_BACKEND_URL environment variables. ' +
              ` Please visit ${this.$branding.docsUrl} ` +
              ' on how to fix this error.'
          )
        }
      }
    }
  },
  methods: {
    fieldHasErrors(fieldName) {
      return this.v$.values[fieldName]?.$error || false
    },
    focusOnFirstError() {
      const firstError = this.$el.querySelector('[data-form-error]')
      if (firstError) {
        firstError.scrollIntoView({ behavior: 'smooth' })
      }
    },
    async login() {
      this.v$.$touch()
      const formValid = await this.v$.$validate()
      if (!formValid) {
        this.focusOnFirstError()
        return
      }

      this.loading = true
      this.hideError()

      try {
        const data = await this.$store.dispatch('auth/login', {
          email: this.values.email,
          password: this.values.password,
        })
        if (data.two_factor_auth) {
          this.$emit(
            'two-factor-auth',
            data.two_factor_auth,
            this.values.email,
            data.token
          )
          return
        }

        this.$i18n.setLocale(data.language)
        this.$emit('success')
      } catch (error) {
        if (error.handler) {
          const response = error.handler.response
          if (response && response.status === 401) {
            if (response.data?.error === 'ERROR_DEACTIVATED_USER') {
              this.showError(
                this.$t('error.disabledAccountTitle'),
                this.$t('error.disabledAccountMessage')
              )
            } else if (
              response.data?.error === 'ERROR_AUTH_PROVIDER_DISABLED'
            ) {
              this.showError(
                this.$t('clientHandler.disabledPasswordProviderTitle'),
                this.$t('clientHandler.disabledPasswordProviderMessage')
              )
            } else if (
              response.data?.error === 'ERROR_EMAIL_VERIFICATION_REQUIRED'
            ) {
              this.$emit('email-not-verified', this.values.email)
            } else {
              this.showError(
                this.$t('error.incorrectCredentialTitle'),
                this.$t('error.incorrectCredentialMessage')
              )
            }

            this.values.password = ''
            this.v$.$reset()
            this.$refs.password.focus()
          } else {
            const message = error.handler.getMessage('login')
            this.showError(message)
          }

          this.loading = false
          error.handler.handled()
        } else {
          throw error
        }
      }
    },
  },
}
</script>
