<template>
  <div>
    <Toasts></Toasts>
    <div class="auth__container">
      <slot />
      <div v-if="versionLabel" class="auth__version" :title="versionTitle">
        {{ versionLabel }}
      </div>
    </div>
  </div>
</template>

<script>
import { useHead } from '#imports'
import Toasts from '@baserow/modules/core/components/toasts/Toasts'
import { buildLabel, buildTitle } from '@baserow/modules/core/utils/buildInfo'

export default {
  components: { Toasts },
  setup() {
    useHead({
      bodyAttrs: { class: 'auth__body' },
    })
  },
  computed: {
    // Rendered once here so every login flow page carries it. Empty on a
    // development build, which hides the element entirely.
    versionLabel() {
      return buildLabel(this.$buildInfo)
    },
    versionTitle() {
      return buildTitle(this.$buildInfo)
    },
  },
}
</script>
