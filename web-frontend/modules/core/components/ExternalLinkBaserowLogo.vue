<template>
  <a
    v-if="$branding.showAttribution"
    :href="$branding.siteUrl"
    target="_blank"
    :title="$branding.siteTitle"
  >
    <Logo height="14" :alt="$branding.siteTitle" />
  </a>
</template>

<script>
export default {
  name: 'ExternalLinkBaserowLogo',
}
</script>
