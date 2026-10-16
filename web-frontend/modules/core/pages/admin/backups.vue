<template>
  <BackupsAdminPanel></BackupsAdminPanel>
</template>

<script>
import { useHead } from '#imports'
import { useNuxtApp } from '#app'
import BackupsAdminPanel from '@baserow/modules/core/components/admin/backups/BackupsAdminPanel'

export default {
  components: { BackupsAdminPanel },
  layout: 'app',
  middleware: 'staff',
  setup() {
    const { $i18n } = useNuxtApp()
    useHead({ title: $i18n.t('adminType.backups') })
  },
}
</script>
