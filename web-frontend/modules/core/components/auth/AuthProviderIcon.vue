<template>
  <img v-if="icon" :src="icon" class="auth-provider-icon" alt="" />
</template>

<script>
export default {
  name: 'AuthProviderIcon',
  props: {
    icon: {
      type: String,
      required: true,
    },
  },
}
</script>
