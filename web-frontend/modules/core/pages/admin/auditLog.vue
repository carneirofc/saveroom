<template>
  <AuditLogAdminTable></AuditLogAdminTable>
</template>

<script>
import { useHead } from '#imports'
import { useNuxtApp } from '#app'
import AuditLogAdminTable from '@baserow/modules/core/components/admin/auditLog/AuditLogAdminTable'

export default {
  components: { AuditLogAdminTable },
  layout: 'app',
  middleware: 'staff',
  setup() {
    const { $i18n } = useNuxtApp()
    useHead({ title: $i18n.t('adminType.auditLog') })
  },
}
</script>
