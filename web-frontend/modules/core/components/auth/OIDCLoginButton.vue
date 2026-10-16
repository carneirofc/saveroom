<template>
  <Button
    tag="a"
    :href="loginUrl"
    target="_self"
    type="secondary"
    full-width
    size="large"
  >
    <AuthProviderIcon :icon="icon" />
    <span v-if="!small"> {{ $t('loginButton.continueWith') }} {{ name }}</span>
  </Button>
</template>

<script>
import AuthProviderIcon from '@baserow/modules/core/components/auth/AuthProviderIcon.vue'

export default {
  name: 'OIDCLoginButton',
  components: { AuthProviderIcon },
  props: {
    redirectUrl: {
      type: String,
      required: true,
    },
    name: {
      type: String,
      required: true,
    },
    icon: {
      type: String,
      required: true,
    },
    small: {
      type: Boolean,
      default: false,
      required: false,
    },
  },
  computed: {
    loginUrl() {
      return new URL(this.redirectUrl).toString()
    },
  },
}
</script>
