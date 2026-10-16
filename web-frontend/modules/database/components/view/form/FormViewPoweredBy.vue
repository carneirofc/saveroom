<template>
  <div v-if="$branding.showAttribution" class="form-view__powered-by">
    {{ $t('formViewPoweredBy.poweredBy') }}
    <a :href="$branding.siteUrl" target="_blank" :title="$branding.siteTitle">
      <Logo class="form-view__powered-by-logo" :alt="$branding.siteTitle" />
    </a>
  </div>
</template>

<script>
export default {
  name: 'FormViewPoweredBy',
}
</script>
