<template>
  <component :is="getComponent()" v-if="getComponent()"></component>
  <template v-else>
    <div class="logo">
      <img :src="logoUrl" v-bind="$attrs" :class="[$attrs.class]" />
    </div>
  </template>
</template>

<script>
export default {
  name: 'Logo',
  data() {
    return {
      // Served by the runtime branding assets route, so it can be replaced by
      // putting img/logo.svg in the branding directory. Bound (not a static
      // `src`) so the template compiler doesn't turn it into a build import.
      logoUrl: '/_branding/assets/img/logo.svg',
    }
  },
  methods: {
    getComponent() {
      return (
        Object.values(this.$registry.getAll('plugin'))
          .filter((plugin) => plugin.getLogoComponent() !== null)
          .sort(
            (p1, p2) => p2.getLogoComponentOrder() - p1.getLogoComponentOrder()
          )
          .map((plugin) => plugin.getLogoComponent())[0] || null
      )
    },
  },
}
</script>
